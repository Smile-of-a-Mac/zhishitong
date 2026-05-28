# 智审通 — 运维与故障排查手册

> 适用版本: v0.3.0+  
> 目标读者: 系统管理员、运维工程师、技术支持人员

---

## 1. 系统架构速览

```
┌─────────────────────────────────────────────────────┐
│                    用户浏览器                          │
│                  http://localhost:8080                │
└──────────────┬──────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────┐
│              zhishitong 容器 (Python/FastAPI)          │
│  ┌──────────┐ ┌────────────┐ ┌────────────────────┐ │
│  │ 认证模块  │ │  OCR 路由   │ │  LangGraph 审批引擎 │ │
│  ├──────────┤ ├────────────┤ ├────────────────────┤ │
│  │ 部门管理  │ │ 管理员路由  │ │ 监控路由 + 日志系统  │ │
│  └──────────┘ └─────┬──────┘ └────────────────────┘ │
│                      │                                │
│  ┌───────────────────▼─────────────────────────────┐ │
│  │            OCR 分级策略                           │ │
│  │  Free → EasyOCR + 本地推理 (18080)                │ │
│  │  Pro  → 外部 LLM API（有配额）                    │ │
│  │  Pro+ → 外部 LLM API（无限制）                    │ │
│  └─────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────┐ │
│  │           结构化日志 → SQLite system_logs         │ │
│  └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────┐
│  inference 容器 (推理服务 :18080)     │
│  Qwen2.5-0.5B-Instruct              │
│  模型路径: /models/... (挂载)        │
└─────────────────────────────────────┘
```

**关键端口：**
| 端口 | 服务 | 说明 |
|------|------|------|
| 8080 | 智审通主服务 | Web UI + API |
| 18080 | 本地推理服务 | Qwen2.5-0.5B JSON 填充 |

---

## 2. 管理员监控面板

访问路径：登录管理员账号 → 左侧导航「系统监控」

面板包含三个标签页：

### 2.1 📊 概览
- **系统状态横幅**：healthy（绿色）/ degraded（黄色）/ critical（红色）
- **服务卡片**：推理服务、EasyOCR、API Key 池、数据库各自状态
- **统计卡片**：总用户、今日新增、今日 OCR 调用、今日审批、24h 错误数
- **分布图**：OCR 按层级分布、审批按状态分布

### 2.2 📋 日志
- 实时查看结构化日志
- 支持按**分类**（认证/OCR/审批/管理/系统/推理）和**级别**（INFO/WARNING/ERROR/CRITICAL）筛选
- 每条日志包含：时间戳、级别、分类、消息、耗时、关联用户

### 2.3 ❌ 错误
- 近 24 小时错误去重聚合
- 显示错误分类、消息、出现次数
- 点击可查看详细堆栈

---

## 3. 常见问题排查

### 3.1 免费用户 OCR 失败

**症状**：免费用户上传图片后返回 500 或 `filled_json` 中包含 `"error": "填充失败"`

**排查步骤**：
1. 打开监控面板 → 概览 → 检查「推理服务」和「EasyOCR」状态
2. 如果推理服务状态为 `down`：
   ```bash
   # 检查推理容器是否运行
   docker ps | grep inference
   # 查看推理服务日志
   docker logs zhishitong_inference_1
   ```
3. 如果 EasyOCR 状态为 `down`：
   ```bash
   # 进入主容器检查
   docker exec -it zhishitong_zhishitong_1 python -c "import easyocr; print('OK')"
   ```
4. 检查日志标签「错误」页签，按 `ocr` 分类筛选

**常见原因**：
| 原因 | 解决方案 |
|------|----------|
| 推理容器未启动 | `docker compose up -d inference` |
| 模型文件未挂载 | 检查 `docker-compose.yml` 中 `volumes` 路径 |
| EasyOCR 未安装 | 重建镜像：`docker compose build --no-cache zhishitong` |
| 内存不足 | 0.5B 模型需约 2GB RAM，检查 `docker stats` |

### 3.2 Pro 用户外部 LLM 调用失败

**症状**：Pro/Pro+ 用户 OCR 返回本地 EasyOCR 结果（降级），而非 LLM 结果

**排查步骤**：
1. 管理员 → API Key → 检查 OCR 类型 Key 是否存在且状态正常（🟢）
2. 检查 Key 对应的 API Base 和模型是否可访问：
   ```bash
   curl -s {API_BASE}/chat/completions \
     -H "Authorization: Bearer {API_KEY}" \
     -d '{"model":"{MODEL}","messages":[{"role":"user","content":"hi"}]}'
   ```
3. 监控面板 → 错误 → 筛选 `ocr` 分类，查看具体报错

**常见原因**：
| 原因 | 解决方案 |
|------|----------|
| API Key 余额不足 | 联系供应商充值 |
| API Base 地址错误 | 修改为正确地址（管理员 → API Key → 编辑） |
| 模型不支持多模态 | 检查模型名是否支持 vision（如 `qwen-vl-plus`） |
| 网络不通 | 检查容器是否能访问外网：`docker exec zhishitong_zhishitong_1 curl -I https://api.example.com` |

### 3.3 审批流程卡住

**症状**：提交审批后长时间无响应或返回 500

**排查步骤**：
1. 监控面板 → 日志 → 筛选 `approval` 分类
2. 查看是否有 `审批流程异常` 错误
3. 检查审批记录状态：
   ```bash
   # 进入容器
   docker exec -it zhishitong_zhishitong_1 python -c "
   from database import SessionLocal
   from models import ApprovalRecord
   db = SessionLocal()
   records = db.query(ApprovalRecord).order_by(ApprovalRecord.created_at.desc()).limit(5).all()
   for r in records:
       print(r.id, r.status, r.decision_reason)
   "
   ```

### 3.4 用户无法登录

**症状**：登录返回 401（用户名或密码错误）或 403（账号已禁用）

**排查步骤**：
1. 监控面板 → 日志 → 筛选 `auth` 分类
2. 查找 `登录失败` 或 `已禁用用户尝试登录` 日志
3. 管理员 → 用户管理 → 检查用户状态是否为「启用」

### 3.5 部门管理员看不到事务

**症状**：部门管理员登录后，「部门事务」列表为空或看不到预期数据

**排查步骤**：
1. 确认管理员所属部门：超级管理员 → 用户管理 → 查看 `is_dept_admin` 和 `department` 字段
2. 确认目标用户是否属于同一部门（`department` 字段匹配）
3. 检查事务 `hard_deleted` 标记是否为 False

### 3.6 数据库问题

**症状**：任何接口返回 500，日志中有 `sqlalchemy` 相关错误

**排查步骤**：
```bash
# 检查数据库文件完整性
docker exec -it zhishitong_zhishitong_1 ls -la /app/data/zhishitong.db

# 备份数据库
docker cp zhishitong_zhishitong_1:/app/data/zhishitong.db ./backup_zhishitong.db

# 如需重置（谨慎！这会丢失所有数据）
docker compose down -v
docker compose up -d
```

---

## 4. 日志格式参考

每条系统日志的 JSON 结构：

```json
{
  "id": 42,
  "timestamp": "2026-05-26T10:58:56.178462Z",
  "category": "ocr",
  "level": "info",
  "message": "OCR 完成: receipt.png",
  "user_id": 2,
  "record_id": 15,
  "duration_ms": 3200,
  "error_trace": null,
  "extra": {
    "tier": "free",
    "provider": "local_easyocr",
    "model": "easyocr+qwen3-0.5b",
    "doc_type": "reimbursement",
    "text_len": 156,
    "has_filled_json": true
  }
}
```

| 字段 | 说明 |
|------|------|
| `category` | `auth`/`ocr`/`approval`/`admin`/`system`/`inference` |
| `level` | `info`/`warning`/`error`/`critical` |
| `message` | 人类可读的描述 |
| `user_id` | 关联用户 ID（可为空） |
| `duration_ms` | 操作耗时（毫秒） |
| `error_trace` | Python 异常堆栈（仅 error 级别） |
| `extra` | 结构化附加信息 |

---

## 5. 日志级别说明

| 级别 | 含义 | 管理员需要关注？ |
|------|------|:---:|
| DEBUG | 调试信息 | 否 |
| INFO | 正常操作记录（登录、OCR 完成、审批通过） | 否 |
| WARNING | 非致命异常（配额用尽、降级、登录失败） | 偶尔 |
| ERROR | 功能异常（OCR 失败、推理服务宕机） | ✅ 是 |
| CRITICAL | 系统级故障（数据库损坏、无法启动） | ✅ 立即 |

---

## 6. 快速诊断命令

```bash
# 1. 系统整体状态
curl -s http://localhost:8080/api/health | python3 -m json.tool

# 2. 管理员登录获取 token
TOKEN=$(curl -s http://localhost:8080/api/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 3. 服务健康检查
curl -s http://localhost:8080/api/admin/monitor/health \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# 4. 最近错误
curl -s "http://localhost:8080/api/admin/monitor/errors?hours=24" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# 5. OCR 分类日志
curl -s "http://localhost:8080/api/admin/monitor/logs?category=ocr&level=error&limit=20" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# 6. 推理服务直接测试
curl -s http://localhost:18080/health
curl -s -X POST http://localhost:18080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"返回JSON: {\"test\": true}"}],"max_tokens":64}'
```

---

## 7. Docker 常用运维命令

```bash
# 查看所有容器状态
docker compose ps

# 查看主服务日志（实时）
docker compose logs -f zhishitong

# 查看推理服务日志
docker compose logs -f inference

# 重启服务
docker compose restart zhishitong

# 重建并重启（代码更新后）
docker compose up -d --build

# 进入容器调试
docker exec -it zhishitong_zhishitong_1 /bin/bash

# 资源监控
docker stats
```

---

## 8. 备份与恢复

```bash
# 备份数据库和上传文件
docker cp zhishitong_zhishitong_1:/app/data ./backup/data_$(date +%Y%m%d)
docker cp zhishitong_zhishitong_1:/app/uploads ./backup/uploads_$(date +%Y%m%d)

# 恢复
docker cp ./backup/data_20260526 zhishitong_zhishitong_1:/app/data
docker cp ./backup/uploads_20260526 zhishitong_zhishitong_1:/app/uploads
docker compose restart zhishitong
```

---

## 9. 告警阈值建议

| 指标 | 警告 | 严重 |
|------|------|------|
| 推理服务不可达 | 连续 2 次检查失败 | 连续 5 次 |
| 24h 错误数 | > 10 | > 50 |
| 磁盘使用率 | > 70% | > 85% |
| API Key 池活跃数 | < 2 | 0 |
| 单次 OCR 耗时 | > 10s | > 30s |

---

*文档版本: 1.0 | 最后更新: 2026-05-26*
