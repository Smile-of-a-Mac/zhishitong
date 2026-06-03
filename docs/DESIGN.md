# 智审通 — 产品设计文档

> 状态：**迭代中**
> 最后更新：2026-06-03

## 📐 设计图集

所有 UML 图的 SVG 渲染版本位于 `docs/diagrams/`，也可通过 `docs/usecase.html` 在浏览器中统一查看。

| 图名 | 文件 | 说明 |
|------|------|------|
| 📋 用例图 | `usecase.puml` → `diagrams/usecase.svg` | 按角色划分的完整用例图（5 类角色 × 30+ 用例） |
| 🏗️ 系统架构图 | `architecture.puml` → `diagrams/architecture.svg` | 前端/后端/服务/数据/AI 推理/LoRA 六层架构 |
| 🔄 审批状态机 | `state_approval.puml` → `diagrams/state_approval.svg` | pending/approved/rejected/needs_revision/cancelled/withdrawn 六态流转 |
| 📝 审批时序图 | `sequence_approval.puml` → `diagrams/sequence_approval.svg` | 以报销为例的多阶段审批完整时序（部门→财务→学校） |
| 📷 OCR 时序图 | `sequence_ocr.puml` → `diagrams/sequence_ocr.svg` | Free/Pro 多级降级 OCR 处理流程 |
| 🗃️ 数据模型类图 | `class_diagram.puml` → `diagrams/class_diagram.svg` | 15 张数据表 + 枚举 + 关系 |
| 🧪 LoRA 管线 | `activity_lora.puml` → `diagrams/activity_lora.svg` | 数据制备→训练→合并→GGUF 转换→推理部署 |
| 🚀 部署架构图 | `deployment.puml` → `diagrams/deployment.svg` | 本地开发 + Docker 部署方案 |

---

## 一、用户分级体系（Free/Pro 两级 + 管理角色）

> **设计原则：** 即使是 4B 参数的小模型，多模态看图识字能力也有限（手写体、表格、复杂发票不可靠）。
> 因此 Free 层采用 **EasyOCR 提取文字 → 本地模型做纯文本 JSON 填充**，而非直接看图。

### 0. 角色体系

| 角色 | 权限 | 说明 |
|------|------|------|
| **普通用户** (Free/Pro) | 上传文档、OCR、提交审批、查看历史、编辑个人信息 | 按学校套餐分级 |
| **部门管理员** (`is_dept_admin`) | 查看本校事务、部门级审批(通过/不通过/需修改) | 不能提交请求、不能删数据 |
| **财务管理员** (`is_finance_admin`) | 报销类事务的财务审批（finance_review 阶段） | 仅处理财务环节 |
| **学校管理员** (`is_school_admin`) | 管理各部门管理员、全校事务总览、学校级审批 | 不直接管理部门事务 |
| **信息管理员** (`is_admin`) | API Key 池、数据管理、系统监控 | 属于信息中心，不管理用户套餐，不参与审批 |

**角色权限边界：**
- ✅ 普通用户：上传文档 → OCR → 查看 AI 分析 → 提交审批 → 查看历史
- ✅ 部门管理员：查看审批队列 → 审阅 AI 建议/缺失信息 → 人工决定（通过/不通过/需修改）
- ✅ 学校管理员：创建/编辑/删除各部门管理员 → 全校事务总览 → 学校级审批（school_review 阶段）
- ❌ 管理员角色（部门/学校/信息）均不能提交审批请求
- ❌ 部门管理员不能删除数据、不能管理用户
- ❌ 信息管理员不管理用户套餐，不参与审批流程

### 1. 审批流程

**核心原则：AI 不替人做决定。** 系统自动核验规则并填写表单，最终审批权始终在部门管理员手上。

| 状态 | 含义 | 谁设定 |
|------|------|--------|
| `pending` | 已提交，AI 分析完成，等待人工审批 | 系统自动 |
| `approved` | 审批通过（可能经过多阶段） | 审批人 |
| `rejected` | 审批驳回 | 审批人 |
| `needs_revision` | 标记需修改补交 | 审批人 |
| `withdrawn` | 用户撤回（可重新编辑提交） | 用户 |
| `cancelled` | 已取消/结案 | 用户或系统 |

LLM 辅助引擎输出：
- 📋 **自动填写表单**：基于 OCR 提取的数据填充审批表单
- 💡 **修改建议**：逐条给出改进意见
- ⚠️ **缺失信息**：标记必填字段中的空白项
- 📜 **引用规则**：列出相关制度条文供管理员参考

|          |      Free 免费版              |     Pro 专业版           |
|----------|-----------------------------|-------------------------|
| **文字提取** | EasyOCR（本地，ARM/x86通用）+ PDF 文本提取 | 多模态 LLM API（看图）   |
| **JSON 填充** | 云端 LLM 优先，规则兜底      | 同一 LLM 完成（一步到位）|
| **调用次数**  | 无限制（纯本地，无外部依赖）   | 管理员设定月度配额      |
| **用户编辑**  | ✅ 前端可编辑表单            | ✅ 同 Free              |
| **适用场景**  | 日常轻度使用 / 个人           | 高频审批部门            |

### 1.1 Free 工作流（两步走：EasyOCR 提取 + 小模型填充）

```
用户上传图片
      │
      ▼
┌──────────────────────────┐
│ Step 0: 图片预处理        │  ← EXIF 修正、最大边 1800px、JPEG 85 压缩
└─────────┬────────────────┘
          ▼
┌──────────────────────────┐
│ Step 1: EasyOCR 文字提取  │  ← 纯 CPU，ARM/x86 原生支持
│                          │    对标准印刷体精度 ≥ 95%
│ 输出: "发票号码: 123456  │    对手写体精度 ~85%（能用但需人工复核）
│        金额: ¥500.00      │
│        日期: 2026-05-20"  │
└─────────┬────────────────┘
          │ 纯文本（不是图片）
          ▼
┌──────────────────────────┐
│ Step 2: 云端 LLM / 规则兜底│  ← 表单预填走云端，日期/地点规则兜底
│ 输入: EasyOCR 提取的文本  │    通过 llama.cpp (llama-cpp-python) 运行
│ 输出: 结构化 JSON          │    纯文本填充，4B 参数轻松胜任
│                          │
│ {                        │
│   "document_type": "报销",│
│   "applicant": "张三",   │
│   "amount": 500.00,      │
│   "date": "2026-05-20",  │
│   "reason": "办公用品"   │
│ }                        │
└─────────┬────────────────┘
          │
          ▼
┌──────────────────────────┐
│ 前端展示可编辑 JSON       │
│ ┌──────────────────────┐ │
│ │ 申请人: [张三  ✏️]   │ │  ← 用户可检查、修改
│ │ 金额:   [500.00 ✏️]  │ │
│ │ 日期:   [2026-05-20] │ │
│ │ 事由:   [办公用品 ✏️]│ │
│ └──────────────────────┘ │
│  [确认提交]  [重新识别]   │
└──────────────────────────┘
```

### 1.2 Pro 工作流

```
用户上传图片
      │
      ▼
┌─────────────────────────────┐
│ 图片预处理 + 检查配额        │
│ EXIF 修正 / 最大边 1800px   │
│ JPEG 85 压缩（降低请求体积） │
└─────────┬───────────────────┘
          │
          ▼
┌─────────────────────────────┐
│ 外部 LLM API 调用            │
│ (管理员配置的 API Key)      │
│                             │
│ 步骤一: 多模态识别 (OCR)     │
│ 步骤二: 结构化 JSON 填充     │
│                             │
│ 优势:                       │
│ - 识别精度 >> 本地模型      │
│ - 理解上下文(发票/请假条等)  │
│ - 自动纠错和格式化          │
└─────────┬───────────────────┘
          │
          ▼
┌─────────────────────────────┐
│ 前端展示可编辑表单           │
│ (同 Free，用户可修改)       │
└─────────────────────────────┘
```

### 1.3 OCR 图片预处理（v0.6.2 新增）

为降低 EasyOCR CPU 处理时间和多模态 LLM 请求体积，所有图片型 OCR 输入都会先经过轻量预处理：

| 步骤 | 说明 |
|------|------|
| EXIF 方向修正 | 使用 `ImageOps.exif_transpose` 修正手机拍照旋转问题 |
| 尺寸压缩 | 最大边缩放到 1800px，保留长宽比 |
| 格式统一 | 转为 RGB JPEG，质量 85，透明图铺白底 |
| 扫描 PDF | `pymupdf` 转首页图片后同样进入预处理链路 |
| 多模态请求 | data URI 使用压缩后的 `image/jpeg`，不再固定 `image/png` |

> 暂不降低多模态 `max_tokens`：当前部分模型会把最终 JSON 放在 `reasoning_content` 中，直接压低 token 可能截断 JSON。后续可评估「低 token 首试 + JSON 解析失败高 token 重试」策略。

---

## 二、本地小模型方案（纯文本 JSON 填充，不做多模态）

### 2.1 为什么不让小模型直接看图？

| 任务 | 本地小模型多模态能力 | 实用结论 |
|------|:--------------:|---------|
| 印刷体发票 OCR | ❌ 不可靠 | 视觉编码需要专门的多模态大模型 |
| 手写请假条 | ❌ 完全不可读 | 手写体本身就需要大模型才能处理 |
| 扫描件/表格 | ❌ 无法解析结构 | 表格区域检测需要专门模型 |
| **纯文本 → JSON 结构化** | ✅ 绰绰有余 | 本地模型专长：阅读文字并结构化填空 |

**结论：用 EasyOCR（专业 OCR 引擎）处理看图，用本地模型处理看字，各取所长。**

### 2.2 候选模型

| 模型 | 参数量 | 内存 | 中文 | 用途 | GGUF 文件名 |
|------|--------|------|:----:|------|------------|
| **Qwen3-14B-Instruct LoRA** | 14B | ~28GB (f16 GGUF) | ⭐⭐⭐⭐⭐ | RAG 合规分析、本地推理兜底 | `qwen3-14b-lora.gguf` |
| **Qwen3-4B-Instruct** | 4B | ~2.5GB (Q4_K_M) | ⭐⭐⭐⭐ | Windows/CUDA/CPU 备选训练与推理 | `qwen3-4b.gguf` |

**当前默认本地推理使用 Qwen3-14B LoRA GGUF**，自然语言填表走云端 LLM；Qwen3-4B PEFT 管线保留为 Windows/CUDA/CPU 备选。

### 2.3 推理引擎选择

| 引擎 | ARM | x86 | Docker 体积 | 预加载 |
|------|:---:|:---:|:----------:|:------:|
| **llama.cpp** | ✅ | ✅ | ~50MB 二进制 | ✅ `--mlock` 锁定内存 |
| Ollama | ✅ | ✅ | ~1GB runtime | ⚠️ 首次调用冷启动 |
| vLLM | ❌ | ✅ | 太重 | ❌ GPU only |

**选 llama-cpp-python**（Python 绑定），通过 uvicorn 暴露 OpenAI 兼容 HTTP API，自动检测 GPU 加速，可常驻后台。

### 2.4 推理服务启动与 GPU 自动检测

推理服务通过 `inference_server/server.py` 启动，自动检测 GPU 加速：

- Apple Silicon → Metal (MPS) 加速
- NVIDIA GPU → CUDA (cuBLAS) 加速
- AMD GPU → ROCm (hipBLAS) 加速
- 无可用 GPU → CPU (AVX2 多线程)

```bash
# 推理服务通过 uvicorn 启动（OpenAI 兼容 API）
PYTHONPATH="$INFER_DIR" uvicorn server:app --host 0.0.0.0 --port 18080

# 环境变量配置
MODEL_PATH=models/qwen3-14b-lora.gguf  # 默认本地推理模型路径
PORT=18080                             # 服务端口
N_CTX=2048                             # 上下文长度
N_THREADS=4                            # CPU 线程数
```

### 2.5 推理服务 API 格式（OpenAI 兼容）

```bash
# 发送文本，返回 JSON
curl http://localhost:18080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role":"user","content":"请从以下发票文字中提取JSON..."}],
    "temperature": 0.1,
    "max_tokens": 512
  }'
```

与外部 LLM API 完全一致的接口！同一个调用层，只需切换 URL——简化后端代码。

### 2.6 Redis 缓存层（v0.5.0 新增）

```
OCR 请求 → SHA256(图片) → Redis 查询
  ├─ 命中 → 直接返回缓存结果（不扣配额，< 1ms）
  └─ 未命中 → 执行 OCR → 写入 Redis（TTL 24h）

API Key 调用计数 → Redis HINCRBY 原子操作
  └─ 失败 ≥ 5 次 → 自动标记 disabled

速率限制 → Redis INCR + EXPIRE
  ├─ Pro:   30 次/分钟
  └─ Free:  10 次/分钟
```

无 Redis 时全静默降级（缓存/计数功能跳过，不影响主流程）。

### 2.7 应用体积估算

```
Free 版本:
  Python 虚拟环境:      ~300 MB
  业务代码 + FastAPI:   ~50 MB
  EasyOCR + 模型:       ~120 MB  (轻量版，纯 CPU wheels)
  llama-cpp-python:     ~50 MB
  本地小模型文件:        ~2.5 GB  (qwen3-4b q4_k_m)
  ─────────────────────────
  合计:                 ~920 MB

Pro 用户如需本地降级，安装 ~200 MB（不含模型）
```

---

## 三、管理员功能

### 3.1 权限矩阵

| 操作 | 普通用户 | 信息管理员 | 学校管理员 | 部门管理员 |
|------|:--------:|:---------:|:---------:|:---------:|
| 上传文件 & OCR | ✅ | ✅ | — | — |
| 查看/编辑自己的 JSON 结果 | ✅ | ✅ | — | — |
| 删除自己的上传内容 | ⚠️ 标记删除 | ✅ 物理删除 | — | — |
| 恢复已标记删除的内容 | ❌ | ✅ | — | — |
| 查看自己的用量统计 | ✅ | ✅ | ✅ | ✅ |
| **添加/删除 LLM API Key** | ❌ | ✅ | ❌ | ❌ |
| **查看所有用户的上传内容** | ❌ | ✅ | ❌ | ❌ |
| **物理删除任意用户数据** | ❌ | ✅ | ❌ | ❌ |
| **创建/管理部门管理员** | ❌ | ❌ | ✅ | ❌ |
| **为本校用户设置学校** | ❌ | ❌ | ✅ | ❌ |
| **查看事务** | ❌ | ✅ 全量 | ✅ 本校全量 | ✅ 本校本部门 |
| **审批（通过/不通过/需修改）** | ❌ | ❌ | ❌ | ✅ |
| **系统监控** | ❌ | ✅ | ❌ | ❌ |

### 3.2 LLM API Key 管理

管理员可添加多个 LLM API Key，系统从池中轮询/负载均衡。

```
┌─────────────────────────────────────────────────────────┐
│  API Key 管理面板                                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  用途分类:                                               │
│  ┌─────────────────────────────────────────────────┐    │
│  │ 📷 OCR 专用 Keys (多模态模型)             15/100 │    │
│  │ ┌──────────┬──────────┬────────┬──────┬──────┐ │    │
│  │ │ 服务商    │ API Key   │ 模型    │ 状态 │ 操作 │ │    │
│  │ ├──────────┼──────────┼────────┼──────┼──────┤ │    │
│  │ │ 阿里百炼  │ sk-***a1 │ qwen-vl│ 🟢   │ 🗑   │ │    │
│  │ │ 火山引擎  │ ak-***b2 │ doubao │ 🟢   │ 🗑   │ │    │
│  │ │ 阿里百炼  │ sk-***c3 │ qwen-vl│ 🔴   │ 🗑   │ │    │
│  │ └──────────┴──────────┴────────┴──────┴──────┘ │    │
│  │ [+ 添加 Key]                         [15/100]  │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │ ✍️ JSON 填充专用 Keys (对话模型)         8/100  │    │
│  │ ┌──────────┬──────────┬────────┬──────┬──────┐ │    │
│  │ │ 阿里百炼  │ sk-***d4 │ qwen   │ 🟢   │ 🗑   │ │    │
│  │ │ DeepSeek │ sk-***e5 │ deepsk │ 🟢   │ 🗑   │ │    │
│  │ └──────────┴──────────┴────────┴──────┴──────┘ │    │
│  │ [+ 添加 Key]                          [8/100]  │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  注意: OCR 和 JSON 填充各最多 100 个 Key                  │
└─────────────────────────────────────────────────────────┘
```

### 3.3 Key 池轮询策略

```
请求到来 → 检查 Key 池:
  ├─ 过滤掉状态为 🔴(失效) 的 Key
  ├─ 剩余 Key 中随机选一个
  ├─ 调用成功 → 返回结果
  └─ 调用失败(限流/余额不足) → 标记该 Key 为 🔴，换下一个重试
                                 如果全部失效 → 返回错误提示管理员
```

### 3.4 添加 Key 弹窗

```
┌─────────────────────────────────────┐
│  添加 LLM API Key                    │
├─────────────────────────────────────┤
│                                     │
│  用途:  [下拉] OCR(多模态) / JSON填充 │
│                                     │
│  服务商: [下拉] 阿里百炼 / 火山引擎   │
│          / DeepSeek / 自定义        │
│                                     │
│  API Base URL: [________________]   │
│  (例如 https://dashscope.aliyuncs   │
│   .com/compatible-mode/v1)          │
│                                     │
│  API Key: [________________]        │
│                                     │
│  默认模型: [________________]       │
│  (例如 qwen-vl-plus)               │
│                                     │
│  备注: [________________]           │
│  (可选，如"经费账号-张三")           │
│                                     │
│  [取消]  [确认添加]                  │
└─────────────────────────────────────┘
```

---

## 四、用户数据管理 & 软删除

### 4.1 数据生命周期

```
用户上传文件
      │
      ▼
文件存储到磁盘/对象存储
      │
      ▼
OCR 识别 & JSON 生成
      │
      ▼
┌───────────────────────────────────┐
│  数据库中记录:                     │
│  - file_id                        │
│  - user_id                        │
│  - original_filename              │
│  - storage_path                   │
│  - ocr_result (JSON)              │
│  - filled_json (可编辑的字段)      │
│  - is_deleted = false  ← 默认     │
│  - deleted_by = null              │
│  - deleted_at = null              │
│  - hard_deleted = false           │
└───────────────────────────────────┘
      │
      ├── 用户点击「删除」
      │       │
      │       ▼
      │   is_deleted = true
      │   deleted_by = "USER"
      │   deleted_at = now()
      │   文件仍保留在磁盘上
      │   【用户端不可见，管理员端可见】
      │
      └── 管理员点击「彻底删除」
              │
              ▼
          物理删除磁盘文件 + 数据库记录
          或: hard_deleted = true (保留审计痕迹)
```

### 4.2 软删除状态机

```
         ┌──────────┐
         │  Active  │ ← 正常使用中（用户和管理员均可见）
         └────┬─────┘
              │ 用户点「删除」
              ▼
         ┌──────────┐
         │ Soft     │ ← 标记删除（仅管理员可见）
         │ Deleted  │   文件仍在磁盘
         └────┬─────┘
              │
    ┌─────────┼─────────┐
    │ 管理员恢复          │ 管理员彻底删除
    ▼                    ▼
┌──────────┐      ┌──────────────┐
│  Active  │      │ Hard Deleted │ ← 文件 + DB 记录清除
│ (恢复)   │      │ (或审计保留)  │
└──────────┘      └──────────────┘
```

### 4.3 管理员数据管理面板

```
┌─────────────────────────────────────────────────────────┐
│  用户数据管理                                            │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  筛选: [用户名▼] [状态: 全部/正常/已删除] [日期范围]      │
│                                                         │
│  ┌────────┬──────────┬──────────┬────────┬────────────┐ │
│  │ 用户    │ 文件名    │ 日期      │ 状态   │ 操作       │ │
│  ├────────┼──────────┼──────────┼────────┼────────────┤ │
│  │ 张三    │ 发票.jpg  │ 05-20    │ 🟢正常 │ 👁查看 🗑  │ │
│  │ 李四    │ 请假.pdf  │ 05-18    │ 🟡已删 │ 👁查看 ↩恢复 │ │
│  │         │          │          │        │    💣彻底  │ │
│  │ 王五    │ 报销.png  │ 05-15    │ 🟢正常 │ 👁查看 🗑  │ │
│  └────────┴──────────┴──────────┴────────┴────────────┘ │
│                                                         │
│  ⚠️ 彻底删除将永久移除文件及数据，不可恢复                │
│                                                         │
│  [批量恢复] [批量彻底删除]                                │
└─────────────────────────────────────────────────────────┘
```

---

## 五、审批流程设计（LangGraph Agent）

> 项目名称是"行政审批自动化 Agent"，OCR 只是第一步，真正的核心是 **审批流程的智能编排**。

### 5.1 完整审批链路

```
用户提交申请
      │
      ▼
┌─────────────────────────────────────────────────────┐
│              LangGraph 审批 Agent                     │
│                                                      │
│  ┌──────────┐    ┌──────────┐    ┌──────────────┐   │
│  │ Node 1   │───▶│ Node 2   │───▶│ Node 3       │   │
│  │ 材料解析  │    │ 规则校验  │    │ 自动决策      │   │
│  │ (OCR+JSON)│    │ (RAG+政策)│    │              │   │
│  └──────────┘    └─────┬────┘    └──────┬───────┘   │
│                        │                │           │
│                  ┌─────▼─────┐    ┌─────▼─────┐     │
│                  │ 材料不全   │    │ 自动批准   │     │
│                  │ → 退回补交 │    │ → 通知流转 │     │
│                  └───────────┘    │ → 归档     │     │
│                                   └───────────┘     │
│                        │                            │
│                  ┌─────▼─────┐                       │
│                  │ 金额超限   │                       │
│                  │ → 转人工   │                       │
│                  └───────────┘                       │
└─────────────────────────────────────────────────────┘
```

### 5.2 LangGraph 状态图设计

```python
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from typing import TypedDict, Literal, Optional
import sqlite3

# ===== 状态定义 =====
class ApprovalState(TypedDict):
    # 输入
    document_type: str           # "报销" / "请假" / "社团申请"
    raw_text: str                # OCR 原始文本
    filled_json: dict            # 结构化 JSON
    attachments: list[str]       # 上传文件路径列表

    # 校验
    issues: list[str]            # 发现的问题列表
    policy_refs: list[str]       # 引用的政策条款

    # 决策
    decision: Optional[str]      # "auto_approve" | "manual_review" | "reject_resubmit"
    reason: Optional[str]        # 决策理由

    # 通知
    notification_sent: bool

# ===== 节点实现 =====
def node_parse_materials(state: ApprovalState) -> ApprovalState:
    """Node 1: 解析材料 → 提取结构化信息"""
    # 这里调用 OCR 服务（EasyOCR 或 LLM API）
    # 将 filled_json 和 document_type 写入 state
    return state

def node_check_rules(state: ApprovalState) -> ApprovalState:
    """Node 2: 规则校验 → 匹配学校政策"""
    # 从 RAG 知识库检索对应政策条款
    # 校验: 金额是否超标? 材料是否齐全? 日期是否合规?
    return state

def node_decide(state: ApprovalState) -> ApprovalState:
    """Node 3: 自动决策 → 三种结果"""
    if len(state["issues"]) == 0:
        state["decision"] = "auto_approve"
        state["reason"] = "材料齐全，符合政策要求"
    elif has_only_minor_issues(state["issues"]):
        state["decision"] = "manual_review"
        state["reason"] = "存在需要人工判断的项目"
    else:
        state["decision"] = "reject_resubmit"
        state["reason"] = "材料不完整，需补充"
    return state

def node_notify(state: ApprovalState) -> ApprovalState:
    """Node 4: 通知流转（站内信 / 邮件）"""
    state["notification_sent"] = True
    return state

# ===== 路由逻辑（条件边） =====
def route_after_check(state: ApprovalState) -> Literal["decide", "reject_resubmit"]:
    if state["issues"] and any("缺失" in i for i in state["issues"]):
        return "reject_resubmit"
    return "decide"

def route_after_decide(state: ApprovalState) -> Literal["notify", "manual_queue"]:
    if state["decision"] == "manual_review":
        return "manual_queue"
    return "notify"

# ===== 构建图 =====
def build_approval_graph():
    builder = StateGraph(ApprovalState)

    builder.add_node("parse", node_parse_materials)
    builder.add_node("check", node_check_rules)
    builder.add_node("decide", node_decide)
    builder.add_node("notify", node_notify)

    builder.set_entry_point("parse")
    builder.add_edge("parse", "check")

    builder.add_conditional_edges("check", route_after_check, {
        "decide": "decide",
        "reject_resubmit": END,
    })

    builder.add_conditional_edges("decide", route_after_decide, {
        "notify": "notify",
        "manual_queue": END,   # 人工审批队列（另一条流程）
    })

    builder.add_edge("notify", END)

    # 持久化状态（断点续跑、人工干预后继续）
    memory = SqliteSaver(sqlite3.connect("approval_checkpoints.db"))
    return builder.compile(checkpointer=memory)
```

### 5.3 五种审批类型的审批规则示例

| 审批类型 | 自动驳回条件 | 转人工条件 | 自动批准条件 |
|---------|------------|-----------|------------|
| **报销** | 无发票附件、金额负数 | 金额 > ¥2000、跨部门 | 金额 ≤ ¥500、标准品目 |
| **请假** | 起止日期倒置、> 7 天无证明 | > 3 天连续请假 | ≤ 1 天、非考试周 |
| **社团申请** | 活动日期与校历冲突 | 涉及校外人员、需场地审批 | 常规社团活动、已有指导老师 |
| **教室借用** | 与课表冲突 | 周末使用、需多媒体设备 | 正常教学时段、空教室 |
| **出差申请** | 无邀请函附件、目的地不明 | 出境、金额 > ¥5000 | 省内、≤ 2 天、标准交通 |

### 5.4 RAG 知识库（审批政策检索）

```
┌─────────────────────────────────────────┐
│  TF-IDF 字符级 n-gram 索引               │
├─────────────────────────────────────────┤
│  chunk_1: 《山东科技大学财务报销管理办法》 │
│           第三章第十二条：单笔报销...      │
│                                           │
│  chunk_2: 《学生请假管理规定》             │
│           第五条：病假需附医院证明...       │
│                                           │
│  chunk_3: 《社团活动审批流程》             │
│           二、(3)：涉及校外人员需...        │
└─────────────────────────────────────────┘
           ▲
           │ 语义检索: "报销金额上限是多少"
           │
    用户请求 → embedding → 检索 top_k 条政策 → 作为 prompt 上下文喂给规则校验节点
```

---

## 六、AES 密钥存储方案

> **问题：** 管理员通过面板添加的 API Key 存储在数据库中，明文存储显然不安全。
> **方案：** 使用 Python `cryptography.fernet` 加解密，密钥通过环境变量注入。

### 6.1 架构

```
┌─────────────────────────────────────────────────┐
│  环境变量                                         │
│  ENCRYPTION_KEY=base64_encoded_32_byte_key       │
│  (docker-compose.yml 或 .env 注入)               │
└───────────────────┬─────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────┐
│  应用层                                           │
│  from cryptography.fernet import Fernet          │
│  f = Fernet(os.environ["ENCRYPTION_KEY"])        │
│                                                   │
│  存: encrypted = f.encrypt(b"api_key_plaintext") │
│  取: plaintext = f.decrypt(encrypted)            │
└───────────────────┬─────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────┐
│  SQLite / PostgreSQL                             │
│  api_keys.api_key = "gAAAAAB..." (密文)          │
│  永远不会以明文形式出现在数据库中                  │
└─────────────────────────────────────────────────┘
```

### 6.2 密钥生成

```bash
# 生成一次性密钥（部署时执行一次）
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# 输出: gvJd... （Base64 字符串，写入 .env 文件）
```

### 6.3 Docker 注入

```yaml
# docker-compose.yml
services:
  backend:
    environment:
      - ENCRYPTION_KEY=${ENCRYPTION_KEY}
      # .env 文件（不加入 Git）:
      # ENCRYPTION_KEY=gvJd...
```

---

## 七、JSON 动态模板渲染

> **问题：** 报销单（金额+发票号）、请假条（起止日期+事由）、社团申请（活动名称+场地）字段完全不同。
> **方案：** 后端定义审批模板 Schema，前端根据 `document_type` 动态渲染对应表单。

### 7.1 后端模板定义（JSON Schema）

```json
{
  "templates": {
    "reimbursement": {
      "label": "报销申请",
      "icon": "💰",
      "fields": [
        { "key": "applicant", "label": "申请人", "type": "text", "required": true },
        { "key": "amount", "label": "报销金额", "type": "number", "required": true, "hint": "单位：元" },
        { "key": "invoice_no", "label": "发票号码", "type": "text", "required": true },
        { "key": "date", "label": "发生日期", "type": "date", "required": true },
        { "key": "category", "label": "费用类别", "type": "select", "options": ["办公用品","差旅","耗材","书籍","其他"] },
        { "key": "reason", "label": "事由说明", "type": "textarea" },
        { "key": "attachments", "label": "附件", "type": "file", "multiple": true, "accept": "image/*,.pdf" }
      ]
    },
    "leave": {
      "label": "请假申请",
      "icon": "📝",
      "fields": [
        { "key": "applicant", "label": "申请人", "type": "text", "required": true },
        { "key": "student_id", "label": "学号/工号", "type": "text", "required": true },
        { "key": "leave_type", "label": "请假类型", "type": "select", "options": ["事假","病假","公假","其他"] },
        { "key": "start_date", "label": "开始日期", "type": "date", "required": true },
        { "key": "end_date", "label": "结束日期", "type": "date", "required": true },
        { "key": "days", "label": "天数", "type": "number", "auto": true },
        { "key": "reason", "label": "事由", "type": "textarea", "required": true }
      ]
    },
    "club_application": {
      "label": "社团活动申请",
      "icon": "🎉",
      "fields": [
        { "key": "club_name", "label": "社团名称", "type": "text", "required": true },
        { "key": "activity", "label": "活动名称", "type": "text", "required": true },
        { "key": "date", "label": "活动日期", "type": "date", "required": true },
        { "key": "venue", "label": "场地需求", "type": "text" },
        { "key": "participants", "label": "预计人数", "type": "number" },
        { "key": "external", "label": "是否涉及校外人员", "type": "boolean" },
        { "key": "description", "label": "活动简介", "type": "textarea", "required": true }
      ]
    }
  },
  "detection_rules": {
    "reimbursement": { "keywords": ["发票","报销","金额","收款"], "weight": 3 },
    "leave":          { "keywords": ["请假","事假","病假","天数"], "weight": 3 },
    "club_application": { "keywords": ["社团","活动","场地","参与者"], "weight": 3 }
  }
}
```

### 7.2 类型自动检测（Free 层用）

```
EasyOCR 提取的文本
      │
      ▼
┌──────────────────────────────────┐
│ 关键词匹配（本地，无需 LLM）:      │
│                                  │
│ 包含"发票+金额" → reimbursement   │
│ 包含"请假+天数" → leave          │
│ 包含"社团+活动" → club_application│
│ 无匹配 → 交给 LLM 判断（Pro层）   │
└──────────────────────────────────┘
```

### 7.3 前端动态表单渲染

```tsx
// 通用方法
function renderField(field: FieldSchema) {
  switch (field.type) {
    case "text":     return <Input />;
    case "number":   return <InputNumber />;
    case "date":     return <DatePicker />;
    case "select":   return <Select options={field.options} />;
    case "textarea": return <TextArea />;
    case "file":     return <Upload />;
    case "boolean":  return <Switch />;
  }
}

// 使用时只需:
<TemplateForm documentType={result.document_type} data={result.filled_json} />
```

---

## 八、文件上传安全

### 8.1 安全策略总览

| 层级 | 策略 | 说明 |
|------|------|------|
| 前端 | 文件类型过滤 | `accept="image/*,.pdf"` + 大小限制 |
| 前端 | 预览时不可执行 | 图片用 `<img>` 渲染；PDF 仅显示文件图标，不在前端内嵌执行 |
| 后端 | MIME 白名单 | 仅允许 image/jpeg, image/png, image/webp, application/pdf |
| 后端 | 魔数校验 | 检查文件头字节（非仅信任扩展名） |
| 后端 | 文件大小上限 | 默认 10MB（可在环境变量配置） |
| 后端 | 文件名清洗 | 去除路径分隔符、特殊字符，生成 UUID 文件名 |
| 存储 | 隔离目录 | 按 `uploads/{user_id}/YYYY-MM/{uuid.ext}` 组织 |
| 存储 | 路径防逃逸 | `resolve_storage_path()` 校验解析路径必须位于 `UPLOAD_DIR` 下 |

### 8.2 后端实现

```python
import uuid, os, magic
from pathlib import Path

ALLOWED_MIMES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

async def validate_and_store(file: UploadFile, user_id: int) -> str:
    content = await file.read()

    # 1. 大小检查
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, f"文件过大，上限 {MAX_FILE_SIZE // 1024 // 1024} MB")

    # 2. MIME 类型检查（基于魔数，非文件扩展名）
    detected = magic.from_buffer(content[:2048], mime=True)
    if detected not in ALLOWED_MIMES:
        raise HTTPException(400, f"不支持的文件类型: {detected}")

    # 3. 文件名清洗 → UUID
    ext = ".pdf" if "pdf" in detected else ".png"
    safe_name = f"{uuid.uuid4().hex}{ext}"

    # 4. 按用户 + 日期隔离存储
    from datetime import date
    today = date.today().strftime("%Y-%m")
    storage = Path("/app/uploads") / str(user_id) / today / safe_name
    storage.parent.mkdir(parents=True, exist_ok=True)
    storage.write_bytes(content)

    return str(storage)
```

### 8.3 Docker 卷挂载安全（规划）

当前本地开发模式通过 MIME 魔数校验、UUID 文件名和路径防逃逸保护上传文件；Docker 部署时建议进一步将上传目录挂载为 `noexec`：

```yaml
# docker-compose.yml
volumes:
  uploads:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /data/zhishitong/uploads

services:
  backend:
    volumes:
      - uploads:/app/uploads:ro,noexec   # noexec 禁止执行上传文件
```

---

## 九、完整数据模型

### 9.1 核心表（节选）

```sql
-- ===== 用户表（扩展） =====
users:
  + llm_ocr_quota:   INT      -- Pro 用户月度 LLM OCR 配额
  + llm_ocr_used:    INT      -- 本月已用次数
  + quota_reset_at:  DATETIME -- 配额重置日期(每月1号)

-- ===== LLM API Key 池 =====
api_keys:
  id:              INT PK
  key_type:        ENUM('ocr', 'json_fill', 'llm')  -- OCR / JSON填充 / RAG与AI通用LLM
  provider:        VARCHAR(64)    -- 阿里百炼 / 火山引擎 / DeepSeek / 自定义
  api_base:        VARCHAR(256)   -- API 地址
  api_key:         VARCHAR(512)   -- 加密存储
  default_model:   VARCHAR(128)   -- 默认模型名
  is_active:       BOOLEAN        -- 是否可用
  fail_count:      INT            -- 连续失败次数
  last_used_at:    DATETIME
  created_by:      INT FK→users  -- 哪个管理员添加的
  created_at:      DATETIME
  note:            VARCHAR(256)   -- 备注

-- ===== 审批记录（核心业务表，实际表名 approval_records） =====
approval_records:
  id:              INT PK
  user_id:         INT FK→users
  original_filename: VARCHAR(256)
  storage_path:    VARCHAR(512)   -- 文件存储路径
  mime_type:       VARCHAR(64)
  file_size:       BIGINT

  ocr_provider:    VARCHAR(32)     -- easyocr/pdf_text/llm_multimodal/local 等
  ocr_model:       VARCHAR(128)   -- 具体模型名
  api_key_id:      INT FK→api_keys NULL  -- 如果走 API，用的哪个 Key

  raw_ocr_text:    TEXT           -- OCR 原始识别文本
  filled_json:     TEXT           -- LLM 填充的结构化 JSON

  -- 审批状态
  document_type:   VARCHAR(32)
  status:          ENUM('pending','approved','rejected','needs_revision','cancelled','withdrawn')
  decision_reason: TEXT           -- LLM 分析摘要 / 审批理由
  policy_refs:     TEXT           -- 引用规则条文
  suggestions:     TEXT           -- LLM 修改建议
  missing_info:    TEXT           -- LLM 标记缺失信息

  current_stage:   VARCHAR(32)    -- dept_review / finance_review / school_review / completed
  stage_history_json: TEXT        -- 阶段历史 JSON（兼容字段）

  -- 软删除字段
  is_deleted:      BOOLEAN DEFAULT FALSE
  deleted_by:      ENUM('USER', 'ADMIN') NULL
  deleted_at:      DATETIME NULL
  hard_deleted:    BOOLEAN DEFAULT FALSE

  created_at:      DATETIME
  updated_at:      DATETIME

-- ===== 管理员操作审计 =====
admin_audit_logs:
  id:              INT PK
  admin_id:        INT FK→users
  action:          VARCHAR(64)    -- 'delete_user_data' / 'add_api_key' / etc
  target_type:     VARCHAR(64)    -- 'approval_record' / 'api_key' / 'user'
  target_id:       INT
  detail:          TEXT
  created_at:      DATETIME

-- ===== 阶段历史（实际表名 approval_stage_histories） =====
approval_stage_histories:
  id:              INT PK
  record_id:       INT FK→approval_records
  stage:           VARCHAR(64)
  status:          VARCHAR(32)
  reviewer_id:     INT FK→users NULL
  reason:          TEXT NULL
  created_at:      DATETIME
```

### 9.2 Key 数量限制实现

```python
# 伪代码
MAX_OCR_KEYS = 100
MAX_FILL_KEYS = 100
MAX_LLM_KEYS = 100

def add_api_key(key_type, ...):
    count = db.query(ApiKey).filter_by(key_type=key_type).count()
    if key_type == "ocr" and count >= MAX_OCR_KEYS:
        raise HTTPException(400, "OCR 专用 Key 已达上限 100 个")
    if key_type == "json_fill" and count >= MAX_FILL_KEYS:
        raise HTTPException(400, "JSON 填充 Key 已达上限 100 个")
    # ... 继续添加
```

---

## 十、前端页面结构

```
智审通 App
├── /login                    # 登录
│
├── / (主工作台)               # 需登录
│   ├── 上传区
│   │   └── 拖拽/点击上传图片
│   ├── 层级标识 (Free/Pro)
│   ├── OCR 结果区
│   │   ├── 原始识别文本
│   │   └── 结构化 JSON 表单（可编辑，请假单为固定字段）
│   └── 历史记录
│       └── 我的上传记录（支持标记删除，可查看详情）
│
├── /profile                  # 个人信息
│   └── 用户名、学校（只读）、部门、角色、层级、LLM 用量、账号状态
│
├── /history                  # 我的事务 / 历史记录
├── /dashboard                # 数据看板（管理员角色）
├── /notifications            # 通知中心
├── /announcements            # 公告制度
├── /resources                # 资源预约
├── /apply/:docType           # 19 类手动申请表单
│
├── /admin/* (信息管理员)       # 需 is_admin 权限
│   ├── /admin/test           # 模拟测试
│   ├── /admin/api-keys       # API Key 管理
│   │   ├── OCR Key 池 (≤100)
│   │   ├── JSON 填充 Key 池 (≤100)
│   │   ├── 添加 Key 弹窗
│   │   └── Key 状态监控（🟢正常 / 🔴停用 / 🗑 永久删除）
│   │
│   ├── /admin/schools        # 学校管理
│   ├── /admin/members        # 成员管理
│   ├── /admin/data           # 用户数据管理
│   │   ├── 所有用户的上传记录
│   │   ├── 软删除管理（恢复/彻底删除）
│   │   └── 筛选（用户名/状态/文档类型）
│   │
│   └── /admin/monitor        # 系统监控
│       └── 审计日志、运行状态
│
├── /dept                     # 事务管理（需 is_dept_admin）
│   └── 本部门审批队列 → 审阅 AI 分析 → 通过/不通过/需修改
│
├── /finance                  # 财务审批（需 is_finance_admin）
│   └── 报销财务环节审批
│
└── /school                   # 学校管理（需 is_school_admin）
    ├── 管理部门管理员账号（增/删/改/查）
    └── /school/affairs       # 全校事务总览与学校级审批
```

---

## 十一、部署架构（二选一）

> **核心原则：** 项目支持本地开发（start.sh 一键启动）和 Docker 容器化两种部署方式。
> 当前以本地开发模式为主（`zhishitong/start.sh`），Docker 部署方案作为未来规划。

### 11.0 环境安装策略（v0.6.3）

**目标：** 安装脚本不替用户“闷头装”，而是先判断本机是否已有依赖、是否具备本地推理和 LoRA 训练能力，再决定安装或跳过。

| 脚本 | 平台 | 职责 |
|------|------|------|
| `setup/setup.sh` | macOS / Linux | 预检、创建 `.venv`、按需安装 Python/npm 依赖、下载模型、初始化数据库、汇总报告 |
| `setup/setup.ps1` | Windows | PowerShell 预检、NVIDIA VRAM 检测、按需安装依赖、下载模型、初始化数据库、汇总报告 |
| `setup/_download_model.py` | 跨平台 | 系统能力检测、HuggingFace 连通性检测、4B 备选 GGUF 下载、进度条显示 |

**能力门槛：**

| 能力 | 最低条件 | 不满足时行为 |
|------|----------|--------------|
| 本地推理 | RAM ≥ 4GB | 跳过本地模型下载，建议使用外部 LLM API |
| 模型下载 | RAM ≥ 4GB、可用磁盘 ≥ 8GB、HuggingFace 可访问 | 不下载模型，在安装报告列出原因 |
| GPU LoRA 训练 | RAM ≥ 8GB、VRAM ≥ 6GB | 跳过训练依赖安装 |
| CPU LoRA 训练 | RAM ≥ 12GB | 跳过训练依赖安装 |

**GPU/VRAM 检测策略：**

| 平台 | 检测方式 |
|------|----------|
| Apple Silicon | 使用统一内存作为 MPS 可用内存估算 |
| Windows / Linux NVIDIA | `nvidia-smi --query-gpu=name,memory.total --format=csv,noheader` |
| 无 NVIDIA 或无法检测 | 允许 CPU 推理，训练按 CPU RAM 门槛判断 |

**模型下载策略：**

`setup/_download_model.py` 默认从 `Qwen/Qwen3-4B-Instruct-GGUF` 选择 `qwen3-4b-instruct-q4_k_m.gguf`，下载后保存为 `models/qwen3-4b.gguf`。下载过程使用显式进度条展示百分比、下载速度、已下载大小和总大小；如 HuggingFace 需要认证，读取 `HF_TOKEN` 或 `HUGGINGFACE_TOKEN`。

### 模型预加载策略（⚠️ 关键）

**问题：** 模型加载到内存需 3-5 秒，如果等到第一次请求再加载会卡住用户。

**解决方案：** `start.sh` 在 FastAPI 启动前，先通过 HTTP 轮询等待推理服务（llama-cpp-python uvicorn）的 `/health` 端点就绪，确保模型已经在内存中。

```bash
# ===== start.sh 中的模型预加载等待逻辑 =====
INFER_READY=0
for i in $(seq 1 60); do
  if curl -sf http://127.0.0.1:18080/health >/dev/null 2>&1; then
    INFER_READY=1
    break
  fi
  sleep 2
done

# 推理服务就绪后再启动后端
PYTHONPATH="$BACKEND_DIR" uvicorn main:app --host 0.0.0.0 --port 8080 --reload &
```

**时间预估：**
| 阶段 | 耗时 | 说明 |
|------|------|------|
| llama-cpp-python 模型加载 | ~3-8s | 4B q4_k_m 约 2.5GB |
| GPU 加速初始化（如有） | ~1-2s | Metal/CUDA/ROCm |
| 首次推理（热身） | ~0.5s | CPU/GPU 执行一次空推理 |
| **总计** | **~3-8s** | 用户第一次请求即热状态 |

---

### 方案 A：本地开发（推荐，当前主力）

适合：演示、功能验证、本地开发、比赛演示
启动方式：`cd zhishitong && bash start.sh`

```
┌────────────────────────────────────────────────────────────┐
│                    本地开发环境                              │
│                    start.sh 启动流程:                       │
│                                                             │
│  1. 虚拟环境检测 + 依赖安装                                  │
│                                                             │
│  2. 推理服务启动（llama-cpp-python + uvicorn :18080）       │
│     ├─ 自动 GPU 检测（Metal/CUDA/ROCm/CPU）                 │
│     ├─ Qwen3-14B LoRA GGUF 模型加载（4B 为跨平台备选）        │
│     └─ 暴露 OpenAI 兼容 API                                 │
│                                                             │
│  3. 后端启动（uvicorn :8080）                                │
│     ├─ 用户管理 / OCR 路由 / API Key 池                     │
│     ├─ Redis 缓存 & 限流（可选）                             │
│     ├─ RAG TF-IDF 政策检索                                  │
│     └─ 审批流程引擎                                         │
│                                                             │
│  4. 前端启动（Vite :5173）                                   │
│                                                             │
│  存储:                                                       │
│    ./zhishitong/data → SQLite 数据库                        │
│    ./uploads → 用户上传文件                                  │
└────────────────────────────────────────────────────────────┘
```

### 方案 B：Docker 容器化（未来规划）

适合：生产部署、团队协作、CI/CD
部署命令：`docker compose up -d`

包含：PostgreSQL 数据库 + 推理服务容器 + FastAPI 后端 + Nginx 反向代理。
Dockerfile 和 docker-compose.yml 待后续补充。

## 十二、学校租户模型（Tenant Model）

> **核心设计：** 甲方是学校，不是个人用户。套餐、配额、数据隔离均以学校（`school` 字段）为租户边界。

### 12.1 学校作为租户

| 概念 | 说明 |
|------|------|
| **租户标识** | `User.school` — 字符串字段，由学校管理员或信息管理员设置 |
| **租户边界** | 同一学校的所有用户共享 `school` 值；不同的 `school` 值代表不同租户 |
| **套餐模式** | **学校级套餐**（即将落地）：一个学校统一订购 Free/Pro，该校所有用户继承 |

### 12.2 学校级套餐与配额继承（设计规划）

当前实现为**用户级套餐**（`User.tier`），后续迁移至学校级套餐的规划如下：

```
学校 (school)
  │
  ├── school_tier:   Free / Pro            ← 学校统一订购
  ├── school_quota:  总 LLM OCR 次数         ← 学校级配额池
  │
  ├── User A
  │     ├── tier:     继承自 school_tier
  │     ├── llm_ocr_quota: school_quota 划分子配额（或按需分配）
  │     └── llm_ocr_used: 个人已用
  │
  └── User B
        ├── tier:     继承自 school_tier
        ├── llm_ocr_quota: 同上
        └── llm_ocr_used: 个人已用
```

**套餐层级的用户感知差异：**

| 层级 | 文字提取 | JSON 填充 | 调用限制 |
|------|---------|-----------|---------|
| **Free** | EasyOCR（本地）+ PDF 文本提取 | 云端自然语言填表 + 本地规则兜底；合规分析走本地 Qwen3-14B | OCR 不限制；云端填表需配置 LLM Key |
| **Pro** | 多模态 LLM API | 同一 LLM | 管理员设定月度配额 |

**过渡策略（从用户级 → 学校级）：**
1. 新增 `SchoolConfig` 表（school / tier / total_quota / used_quota）
2. 种子数据中为每个 `school` 创建一条配置，tier 取该校用户中最高值
3. 前端管理面板增加「学校套餐管理」入口（学校管理员/信息管理员可见）
4. `GET /api/me` 加 `school_tier` 字段

### 12.3 Tenant ID 约束（数据库层）

所有涉及多学校数据的查询，必须在查询层注入 `school` 过滤：

```python
# 当前实现：用户级查询已自带 school 字段
# 规划强制规则（中间件层拦截）：
# 1. 非管理员请求 → 自动附加 school=当前用户.school
# 2. 管理员跨学校查询 → 显式声明 target_school 参数
# 3. 审计日志记录 school 上下文
```

**禁止出现：**
- 不带 `school` 条件的跨表全量扫描（管理员显式声明的除外）
- 直接使用用户 ID 拼接而未验证 school 归属的接口

### 12.4 学校管理员边界

| 能力 | 说明 |
|------|------|
| ✅ 创建/编辑/删除本学校部门管理员 | `school` 与管理员所在学校一致 |
| ✅ 为本学校用户设置/更新 `school` 字段 | 仅限本校范围 |
| ❌ 不能跨学校操作 | 数据库层 + API 层双校验 |
| ❌ 不能删除审批数据 | 无物理删除权限 |
| ❌ 不能修改套餐层级 | 套餐由信息管理员/学校负责人线下确认后配置 |
| ❌ 不能提交审批请求 | 所有管理员角色均禁止 |

---

## 十三、流程版本治理

> **背景：** 审批模板和业务规则会随时间变化（新学期新政策、报销标准调整等）。需要流程版本管理来确保运行中实例不受影响，同时新实例使用最新规则。

### 13.1 流程版本号

```
格式: v<主版本>.<次版本>.<修订号>

v1.0.0  初始版本（当前）
v1.1.0  新增「请假」模板字段变更
v2.0.0  审批规则重大变更（如报销额度算法重构）
```

**版本关联实体：**

| 实体 | 版本管理方式 |
|------|-------------|
| **模板定义** (`templates.json`) | 文件级版本，随部署变更，不单独版本化 |
| **审批规则** (`RULES`) | 硬编码在 `services/approval_service.py`，随代码版本走 |
| **审批记录** (`ApprovalRecord`) | 每条记录记录 `document_type` 和当前 `filled_json` 结构，不显式记录流程版本 |
| **API 接口** | 前缀 `/api/` 不变，向后兼容 |

**当前实现策略：** 模板和规则随代码发布一起更新，不单独做流程版本数据库。运行中的审批实例使用提交时的 `filled_json` 快照，不受模板更新影响。

### 13.2 实例迁移策略

对于**待审批（pending）**的实例，当模板字段发生变化时：

```
场景：请假模板 v1.0 有 applicant/start_date/end_date
      → v1.1 新增 advisor_phone
      → v1.2 移除 student_id

处理策略（当前实现）：
  ┌─ pending 实例 → 使用提交时的 filled_json 快照，不受模板更新影响
  ├─ 新提交的申请 → 使用最新模板
  └─ 管理员审批时 → 展示提交时的快照 + 标注「最新模板差异」
```

**未来规划（版本管理增强）：**

| 版本操作 | 策略 | 状态 |
|---------|------|------|
| 模板字段新增 | 向后兼容，旧实例不受影响 | ✅ 已支持 |
| 模板字段删除 | 旧实例的已填数据仍保留在 `filled_json` 中，仅新提交不再出现 | ✅ 已支持 |
| 模板字段改名 | 需提供字段映射表（`_FIELD_KEY_MAP` 维护） | ✅ 已支持 |
| 规则变更（新必填项） | **不追溯**已有 pending 实例，仅对新提交生效 | ✅ 当前行为 |
| 强制迁移旧实例到新版本 | 需管理员手动确认迁移范围，系统自动补填可映射字段 | ⬜ 待实现 |

### 13.3 回滚策略

```
回滚触发条件：
  1. 新模板导致大量审批异常（人工发现）
  2. 管理员在「系统监控」面板点击「回滚到上一版本」

回滚过程：
  ① 模板文件回退到上一版本（git revert）
  ② 更新 templates.json 并重启后端
  ③ 发布公告：XX 模板已回滚至 vX.X.X
  ④ 受影响的 pending 实例由部门管理员逐一复核

不执行的操作：
  - ❌ 不回滚已完成的审批记录
  - ❌ 不回滚已归档的数据
```

### 13.4 灰度发布（未来规划）

```
┌──────────────────────────────────────────────────┐
│  灰度流程（学校级）                                 │
│                                                    │
│  1. 信息管理员选择「灰度学校」（如：示例大学）       │
│  2. 灰度学校使用新模板/新规则                       │
│  3. 监控灰度学校的审批通过率、API 调用成功率         │
│  4. 运行 24h 无异常 → 全量发布                      │
│  5. 运行异常 → 单学校回滚，不影响其他学校            │
└──────────────────────────────────────────────────┘
```

---

## 十四、审计合规与日志治理

> **原则：** 操作必须可追溯、日志必须防篡改、数据必须可脱敏。

### 14.1 审计层级

| 层级 | 记录内容 | 存储位置 | 保留期限 |
|------|---------|---------|---------|
| **管理员操作审计** | 谁（admin_id）在什么时间做了什么操作 | `admin_audit_logs` 表 | 3 年 |
| **审批操作审计** | 谁审批了哪条记录，状态变更前后 | `approval_records.updated_at` + `admin_audit_logs` | 同审批记录 |
| **系统运行日志** | API 请求/响应、耗时、错误 | `system_logs` 表 | 30 天滚动 |
| **API Key 操作审计** | Key 的添加、停用、删除、启用 | `admin_audit_logs` | 3 年 |
| **用户操作审计** | 用户的提交、取消操作 | `system_logs` + `approval_records` | 同审批记录 |

### 14.2 日志防篡改

```python
# 当前采用「应用层写日志 + 数据库存储」模式
# 防篡改措施（已实现 + 规划）：

# ✅ 已实现：
# - 审计日志通过 AdminAuditLog 模型写入，非开发者无法直接修改数据库
# - 系统运行日志使用 SystemLog 模型，不支持 UPDATE（仅 INSERT + SELECT）
# - 管理员操作与审批记录变更分别在独立表中审计

# ⬜ 规划（v4.1+）：
# - 日志写入使用独立数据库账号（只写、不删、不改）
# - 系统运行日志增加 SHA-256 链式校验（每个 log 行包含上一行 hash）
# - 每日导出不可变日志快照（加密归档至独立存储）
# - 日志访问需要单独的审批流程
```

**禁止行为：**
- ❌ 通过 API 直接删除或修改已生成的审计日志
- ❌ 将管理员操作审计与用户操作日志混存（已隔离）

### 14.3 日志留存期限

| 日志类型 | 在线保留 | 归档 | 销毁 |
|---------|---------|------|------|
| `admin_audit_logs` | 3 年 | 第 4 年导出加密归档 | 第 7 年 |
| `system_logs` | 30 天 | 31-90 天压缩归档 | 第 91 天 |
| `approval_records.hard_deleted` | 标记删除后保留 180 天 | 第 181-365 天归档 | 第 366 天 |
| 文件存储（uploads） | 标记删除后保留 30 天 | — | 第 31 天物理清理 |

### 14.4 数据脱敏

| 字段类型 | 脱敏规则 | 日志中存储 |
|---------|---------|-----------|
| API Key 明文 | Fernet 加密后存储 | 只存密文，不存明文 |
| 用户密码 | bcrypt 哈希 | 只存哈希值 |
| 手机号（`phone`/`advisor_phone`） | 日志中中间四位掩码 `138****1234` | 审批记录中保留完整（业务需要） |
| 学生姓名 | 日志中保留完整（业务需要） | 同左 |
| 文件路径 | UUID 化，去除真实路径 | 只存 UUID 文件名 |
| 用户 IP 地址 | 日志中最后一段掩码 `192.168.1.*` | ⬜ 待实现 |

### 14.5 取证流程

```
事件发生
  │
  ▼
① 信息管理员在「系统监控 → 审计日志」中搜索相关记录
  │  筛选条件: 用户 / 操作类型 / 时间段 / 学校
  │
  ▼
② 导出审计报告（JSON / CSV）
  │  包含: 操作人、操作时间、目标类型、操作详情、学校上下文
  │
  ▼
③ 交叉验证（可选）
  │  - 审批记录: approval_records.status 变更历史
  │  - 系统日志: system_logs 中对应的 API 请求详情
  │  - 文件存储: 确认文件是否被删除/修改
  │
  ▼
④ 输出取证报告
    格式: Markdown / PDF
    内容: 时间线、涉事人员、操作详情、证据快照
```

---

## 十五、RAG + TF-IDF 政策知识库服务（v0.5.0 新增）

> **核心思路：** 从 `data/policy_kb.json` 加载结构化的校规政策知识库，使用 TF-IDF 向量检索替代简单关键词匹配，所有 LLM 调用统一走本地推理服务。

### 15.1 知识库结构

```json
{
  "documents": [
    {
      "id": "sdust_reimbursement",
      "title": "山东科技大学财务报销管理办法",
      "category": "财务",
      "applicable_types": ["reimbursement", "business_trip"],
      "chunks": [
        {
          "id": "reim_001",
          "title": "报销金额限制",
          "text": "单笔报销金额不超过5000元的，由部门负责人审批；超过5000元的，需经财务处审核后报分管校领导审批。",
          "keywords": ["报销", "金额", "5000", "限额"]
        }
      ]
    }
  ]
}
```

### 15.2 检索流程

```
用户提问 "报销金额上限是多少"
      │
      ▼
┌──────────────────────────────────────┐
│ Step 1: 字符级 TF-IDF 向量化          │
│   analyzer="char", ngram_range=(2,4) │
│   中文友好，无需分词器                │
└─────────┬────────────────────────────┘
          │
          ▼
┌──────────────────────────────────────┐
│ Step 2: Cosine Similarity 检索 Top-K │
│   默认返回 top 5 个最相关 chunk       │
└─────────┬────────────────────────────┘
          │
          ▼
┌──────────────────────────────────────┐
│ Step 3: 拼接 Prompt → LLM 生成回答    │
│   system: "你是高校行政审批政策助手"   │
│   context: [检索到的条文原文]          │
│   question: "报销金额上限是多少"       │
└─────────┬────────────────────────────┘
          │
          ▼
        LLM 回答 + 引用来源
```

### 15.3 RAG 服务端点（`routers/rag_router.py`）

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/ai/intent` | POST | 自然语言意图识别 → 推荐文档类型和预填字段 |
| `/api/ai/manual-compliance` | POST | 对学生端手动填表草稿进行提交前合规建议，不创建审批记录 |
| `/api/ai/compliance/{id}` | POST | 对指定审批记录进行合规性 RAG 分析 |
| `/api/ai/similar/{id}` | POST | 检索相似历史案例 |
| `/api/ai/opinion` | POST | 审批意见草稿生成 |
| `/api/ai/chat` | POST | 政策问答 Chatbot（支持多轮对话） |
| `/api/ai/search` | POST | 自然语言搜索 → 返回过滤参数 |

### 15.4 容错降级

```python
# 当 LLM 不可用时，降级为纯规则检索模式
if not llm_available:
    return {
        "answer": "未找到匹配的政策条文",
        "sources": tfidf_search(question, top_k=3),
        "fallback": True
    }
```

---

## 十五半、Human-in-the-Loop (HITL) 架构总览

> **核心设计理念：** AI 在人类监督下执行子任务（文字提取、字段填充、合规分析、意见草稿生成），所有涉及决策和责任的环节保留给人类。系统不存在"全自动审批"路径。

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Human-in-the-Loop 总览                          │
│               ┌──── 虚线 = AI 代理  ──── 实线 = 人类角色 ────┐         │
└─────────────────────────────────────────────────────────────────────────┘

                                ┌──────────────┐
                    ┌──────────▶│  👤 学生/申请人  │◀──────────────────┐
                    │           └───────┬──────┘                    │
                    │                   │                            │
                    │           ╔═══════╧═══════╗                    │
                    │           ║ 上传文件/描述需求  ║                    │
                    │           ╚═══════╤═══════╝                    │
                    │                   │                            │
                    │           ╔═══════╧═══════╗                    │
                    │           ║  ┌─ AI Agent ─┐  ║                    │
                    │           ║  │ OCR 文字提取 │  ║                    │
                    │           ║  │ 字段 JSON 填充│  ║                    │
                    │           ║  └──────┬─────┘  ║                    │
                    │           ╚═══════╤═══════╝                    │
                    │                   │                            │
                    │           ┌───────┴──────┐                     │
                    │           │  👤 人工审查    │                     │
                    │           │  • 校验 AI 字段  │                     │
                    │           │  • 手动修改错误  │                     │
                    │           └───────┬──────┘                     │
                    │                   │                            │
                    │           ╔═══════╧═══════╗                    │
                    │           ║  ┌─ AI Agent ─┐  ║                    │
                    │           ║  │ RAG 合规分析  │  ║                    │
                    │           ║  │ • 风险等级评估 │  ║                    │
                    │           ║  │ • 逐项检查     │  ║                    │
                    │           ║  │ • 政策条文引用 │  ║                    │
                    │           ║  └──────┬─────┘  ║                    │
                    │           ╚═══════╤═══════╝                    │
                    │                   │                            │
                    │           ┌───────┴──────┐                     │
                    │           │  👤 确认提交    │                     │
                    │           │  • 阅读合规建议  │                     │
                    │           │  • 修改不合规项  │                     │
                    │           │  • 提交审批     │                     │
                    │           └───────┬──────┘                     │
                    │                   │                            │
                    │                   ▼                            │
                    │          ┌────────────────┐                    │
                    │          │  📋 审批系统     │                    │
                    │          └───────┬────────┘                    │
                    │                   │                            │
                    │                   ▼                            │
                    │          ┌────────────────┐                    │
                    │          │  👤 部门管理员   │                    │
                    │          └───────┬────────┘                    │
                    │                  │                             │
                    │          ╔═══════╧═══════╗                     │
                    │          ║  ┌─ AI Agent ─┐  ║                     │
                    │          ║  │ 合规分析     │  ║                     │
                    │          ║  │ 相似案例检索  │  ║                     │
                    │          ║  │ 审批意见草稿   │  ║                     │
                    │          ║  └──────┬─────┘  ║                     │
                    │          ╚═══════╤═══════╝                     │
                    │                  │                             │
                    │          ┌───────┴──────┐                      │
                    │          │  👤 管理员决策  │                      │
                    │          └───────┬──────┘                      │
                    │                  │                             │
                    │      ┌───────────┼───────────┐                 │
                    │      ▼           ▼           ▼                 │
                    │  ┌────────┐ ┌────────┐ ┌────────┐             │
                    │  │ ✅ 通过 │ │ ❌ 驳回 │ │ 📝 需修改│──┐          │
                    │  └────────┘ └────────┘ └────────┘  │          │
                    │      │           │            │     │          │
                    │      ▼           ▼            │     │          │
                    │  ┌────────┐ ┌────────┐        │     │          │
                    │  │ 💰 财务  │ │  结束   │        │     │          │
                    │  │ 管理员   │ │        │        │     │          │
                    │  └────┬───┘ └────────┘        │     │          │
                    │       ▼                       │     │          │
                    │  ┌──────────┐                 │     │          │
                    │  │ 🏫 学校   │                 │     │          │
                    │  │ 管理员    │                 │     │          │
                    │  └────┬─────┘                 │     │          │
                    │       ▼                       │     │          │
                    │  ┌────────┐                    │     │          │
                    │  │ ✅ 完结  │                    │     │          │
                    │  └────────┘                    │     │          │
                    │                                │     │          │
                    └────────────────────────────────┘─────┘          │
                                                       │              │
                                                       ▼              │
                                              ┌──────────────┐        │
                                              │  👤 学生重新    │────────┘
                                              │  编辑后重提    │
                                              └──────────────┘
```

**图中各环节的 HITL 约束：**

| 阶段 | AI 做 | 人做 | 决策权 |
|------|-------|------|--------|
| 填表辅助 | OCR 文字提取、JSON 字段填充 | 校验修改 AI 提取结果 | 人 |
| 合规自查 | 政策检索、风险等级判断、建议生成 | 采纳或忽略建议后提交 | 人 |
| 审批审查 | 合规分析、相似案例检索、意见草稿生成 | 阅读分析后做出审批决定 | 人 |
| 结果通知 | 自动生成通知消息并推送 | 查看结果，决定是否修改重提 | 人 |

---

## 十六、智能预审规则引擎（v0.5.0 新增）

> **设计原则：** 在 LLM 分析之前执行硬性规则检查，拦截明显不合规的申请，减少 LLM 调用成本。

### 16.1 规则类型

| 规则类型 | 说明 | 示例 |
|---------|------|------|
| `field_required` | 必填字段检查 | 报销金额不能为空 |
| `field_range` | 数值范围检查 | 报销金额 > 0 且 ≤ 50000 |
| `duplicate_check` | 发票号查重 | 同一发票号不能重复报销 |
| `date_validity` | 日期合法性 | 请假结束日期不能早于开始日期 |

### 16.2 规则配置（`RuleConfig` 模型）

```python
class RuleConfig(Base):
    rule_key: str          # 唯一标识，如 "reim_amount_positive"
    rule_name: str         # 中文名，如 "报销金额为正数"
    document_type: str     # 适用文档类型（null=全局）
    rule_type: str         # field_required / field_range / duplicate_check
    field_key: str         # 校验字段
    operator: str          # gt/lt/gte/lte/eq/contains
    threshold_value: str   # 阈值
    error_message: str     # 不通过提示语
    severity: str          # error(拦截) / warning(提醒)
    is_active: bool        # 是否启用
    priority: int          # 优先级（数字越大越先执行）
```

### 16.3 执行流程

```
审批提交 → check_rules()
  ├─ 加载所有 is_active=True 的规则（按 priority 降序）
  ├─ 逐条执行 _evaluate_rule()
  │   ├─ field_required → 检查字段是否为空
  │   ├─ field_range → 数值与阈值比较
  │   └─ duplicate_check → 数据库查重
  ├─ 收集所有结果
  └─ 返回 { record_id, all_passed, results[] }
```

---

## 十七、站内信通知系统（v0.5.0 新增）

### 17.1 通知类型

| 类型 | 触发时机 | 接收人 |
|------|---------|--------|
| `approval_submitted` | 用户提交新申请 | 对应审批阶段的审批人 |
| `approval_approved` | 审批通过 | 申请人 |
| `approval_rejected` | 审批驳回 | 申请人 |
| `approval_needs_revision` | 标记需修改 | 申请人 |
| `approval_urged` | 申请人催办 | 当前审批人 |
| `approval_overdue` | 超时未处理 | 当前审批人 |
| `stage_advanced` | 进入下一审批阶段 | 申请人 + 下一阶段审批人 |
| `system_announcement` | 系统公告 | 全体或指定用户 |

### 17.2 前端呈现

- **红点角标**：侧栏「通知」菜单项显示未读数
- **通知列表页**：`/notifications`，支持按已读/未读筛选
- **类型区分**：每种通知有独立图标（📩新申请 ✅通过 ❌驳回 📝需修改）和颜色
- **快捷跳转**：点击通知可直接跳转到关联的审批记录详情

---

## 十八、资源预约系统（v0.5.0 新增）

### 18.1 资源类型

| 资源 | 模型 | 字段 |
|------|------|------|
| 📋 **会议室** | `ResourceRoom` | 名称、位置、容纳人数、设备（投影仪/白板/视频会议） |
| 🚗 **公车** | `ResourceVehicle` | 车牌号、车型、座位数、司机 |

### 18.2 预约流程

```
用户浏览可用资源 → 选择时间段 → 填写事由 → 提交预约申请
                                                    │
                                                    ▼
                                            管理员审批 → 通过/驳回
```

- `ResourceBooking` 表统一管理会议室和车辆预约
- 支持按时间段查询冲突检测
- 审批状态：`pending` / `approved` / `rejected` / `cancelled`
- 前端页面：`/resources`，Tab 切换会议室/车辆

---

## 十九、数据看板 Dashboard（v0.5.0 新增）

### 19.1 按角色展示

| 角色 | 可见数据维度 |
|------|------------|
| 普通用户 | 个人提交统计、审批进度 |
| 部门管理员 | 本校审批量、待审数、通过率 |
| 财务管理员 | 报销类事务统计 |
| 学校管理员 | 全校审批概览、各部门对比 |
| 信息管理员 | 全平台数据（所有学校汇总） |

### 19.2 看板指标

- **概览卡片**：总用户、总审批量、待审批数、今日新增
- **趋势图**：近 30 天每日审批量折线图
- **类型分布**：按文档类型（报销/请假/社团等）的饼图
- **状态分布**：pending / approved / rejected / needs_revision 占比
- **效率指标**：平均处理时长、审批通过率、驳回率
- **部门排行**：Top 部门审批量
- **高频申请人**：Top 用户提交量

---

## 二十、公告 & 制度文库（v0.5.0 新增）

### 20.1 公告分类

| 分类 | 说明 |
|------|------|
| `announcement` | 系统公告（维护通知、新功能上线） |
| `policy` | 校规制度（财务管理办法、请假规定等） |
| `guide` | 办事指南（如何报销、如何请假等流程说明） |

### 20.2 功能特性

- **置顶**：`is_pinned=True` 的公告始终排在最前
- **关联文档类型**：公告可关联特定审批类型，在对应申请页展示
- **阅读量统计**：每次查看详情 `view_count += 1`
- **发布/隐藏**：`is_published` 控制是否对外可见
- 前端页面：`/announcements`

---

## 二十一、AI 政策问答助手 ChatBot（v0.5.0 新增）

### 21.1 悬浮面板设计

```
┌──────────────────────────────────┐
│  右下角悬浮按钮 💬                 │
│       ↓ 点击展开                   │
│  ┌─────────────────────────┐     │
│  │  智审通政策助手           │     │
│  │  ─────────────────────  │     │
│  │  用户: 报销需要什么材料？  │     │
│  │  助手: 根据《财务报销管理  │     │
│  │        办法》第三章...     │     │
│  │         📎 引用来源       │     │
│  │  ─────────────────────  │     │
│  │  建议问题:               │     │
│  │  · 报销需要什么材料？     │     │
│  │  · 请假超过3天怎么办？    │     │
│  │  · 差旅住宿费标准是多少？  │     │
│  │  [输入框___________] [发送] │     │
│  └─────────────────────────┘     │
└──────────────────────────────────┘
```

### 21.2 技术实现

- **前端**：React 组件 `AIChatPanel.tsx`，仅登录用户可见
- **聊天记录持久化**：按 `user_id` 隔离存储在 `localStorage`
- **后端**：调用 `/api/ai/chat`，内部走 RAG 检索 + LLM 生成
- **多轮对话**：支持传入 `history` 上下文
- **引用来源**：返回匹配的政策条文原文

---

## 二十二、LoRA 微调管线（v0.5.0 新增）

> **目标：** 用山东科技大学实际事务流程数据微调 Qwen3-14B，使其成为「山科大事务流程专家」。Qwen3-4B/PEFT 管线保留为 Windows/CUDA/CPU 备选。

### 22.1 数据制备

```
data/
├── sdust_classification.jsonl      # 分类语料（100 条，10 类）
└── build_classification_corpus.py   # 分类语料构建脚本
```

### 22.2 训练配置（MLX + Qwen3-14B）

```python
# training/train_lora_mlx.py
BASE_MODEL = "Qwen3-14B (MLX 4bit)"   # 基座模型
LORA_R = 16                            # LoRA 秩
LORA_ALPHA = 32                        # 缩放因子
NUM_EPOCHS = 10                        # 训练轮数
BATCH_SIZE = 1
LEARNING_RATE = 1e-4
MAX_SEQ_LENGTH = 512
VAL_SPLIT = 0.1                        # 10% 验证集
```

### 22.3 产出物

```
lora_output_mlx/
├── adapters.safetensors        # LoRA 适配器权重（847KB）
├── adapter_config.json         # 适配器配置
└── merged_f16/                 # 融合后完整模型（HF f16 格式，~28GB）
    ├── model-*.safetensors
    ├── config.json
    └── tokenizer.json

models/
└── qwen3-14b-lora.gguf         # 最终 GGUF（~28GB，给 llama.cpp 推理用）
```

### 22.4 训练 & 融合 & 转换（一步完成）

```bash
cd /Users/wangdaoyu/VSCode/sito
.venv/bin/python training/train_lora_mlx.py
```

脚本自动完成：训练 → 保存 LoRA 适配器 → 生成 adapter_config.json → 调用 `mlx_lm fuse --dequantize` → 保存 f16 融合模型 → 调用 `convert_hf_to_gguf.py` 输出 GGUF。

### 22.5 start.sh 自动切换

```bash
# start.sh 检测逻辑
if [ -f "$LORA_GGUF" ]; then
  export MODEL_PATH="$LORA_GGUF"  # 使用微调模型
fi
```

当前 `start.sh` 不再负责 HF → GGUF 转换，只检测 `models/qwen3-14b-lora.gguf` 是否存在；转换由训练/合并阶段完成。

---

## 二十三、管理员模拟测试面板（v0.5.0 新增）

> **场景：** 信息管理员需要以任意用户身份登录系统，验证不同角色/套餐下的功能表现，而无需实际切换账号。

### 23.1 功能

| 能力 | 说明 |
|------|------|
| 🔄 **临时切换身份** | 选择目标用户，临时以该用户角色查看系统 |
| 🎛️ **覆盖属性** | 可覆盖 `is_admin`、`tier`、`school`、`department` 等字段 |
| 🚪 **一键退出** | 顶部横幅 + 侧栏提示条均可一键退出模拟，恢复管理员身份 |
| 🔒 **安全隔离** | 模拟覆盖使用 `db.expunge()` 防止误写数据库；管理员登录自动清除模拟状态 |
| 🔄 **自动刷新** | 退出模拟后正确刷新 React 身份上下文并跳回管理员工作台 |

### 23.2 实现细节

- **后端**：`auth.py` 的 `get_current_user` 依赖注入支持模拟覆盖；`get_raw_user` 绕过覆盖用于测试端点
- **前端**：`AdminTestPage.tsx` 面板；`Frame.tsx` 中的 `SimulationBanner` 横幅随路由切换自动刷新
- **状态管理**：模拟状态存储在服务端 Session，非客户端 Cookie，防止篡改

---

## 二十四、推理服务 GPU 自动检测（v0.5.0 新增）

> `inference_server/server.py` 在启动时自动检测最优 GPU 后端，无需手动配置。

### 24.1 检测优先级

| 优先级 | 硬件 | 后端 | 说明 |
|--------|------|------|------|
| 1 | Apple Silicon (M1/M2/M3/M4) | Metal (MPS) | `n_gpu_layers=-1` 全层 GPU |
| 2 | NVIDIA GPU | CUDA (cuBLAS) | 自动检测 `torch.cuda.is_available()` |
| 3 | AMD GPU | ROCm (hipBLAS) | 检测 `torch.hip` 或环境变量 |
| 4 | 无 GPU | CPU (AVX2) | `n_gpu_layers=0`，多线程推理 |

### 24.2 暴露接口

- `POST /v1/chat/completions` — OpenAI 兼容的 Chat API
- `GET /health` — 健康检查端点

---

## 二十五、审批意见模板 & 审批代理（v0.5.0 新增）

### 25.1 审批意见模板（`ApprovalOpinionTemplate`）

审批人可预设常用批语，一键填入审批意见：

| 分类 | 示例模板 |
|------|---------|
| `approve` | "材料齐全，同意报销"、"符合请假规定，批准" |
| `reject` | "发票信息不完整，请补充后重新提交" |
| `revision` | "请补充发票原件照片"、"请假事由需更详细说明" |

### 25.2 审批代理（`ApprovalDelegation`）

审批人休假/出差时可将审批权委托给他人：

- 设置委托时间段（`start_date` ~ `end_date`）
- 委托期间，被委托人可代为审批
- 到期自动失效
- 操作记录可追溯

---

## 二十六、背景动画与 AI 活动状态联动（v0.5.2）

> **设计原则：** 背景动画应当低调、克制，但在 AI 调用时提供可感知的"系统正在推理"反馈。参考 Gemini/ChatGPT 移动端的柔和动态光雾风格，不做 HUD/粒子/扫光等廉价特效。

### 26.1 日常态

- 低饱和智能流体场：6 个大型半透明 gradient blob 做低频正弦叠加漂移
- 各 blob 的运动不是圆周，而是 Perlin-like 多频叠加，形成自然有机感
- 整体以蓝、青、紫、暖白为主，不用黄绿红撞色
- 通过 CSS `blur(34px)` + 低 `opacity` 保持极低存在感，不抢卡片

### 26.2 AI 活跃态

- 所有 blob 向页面中上部隐形焦点聚合（`focusStrength` 插值）
- 速度提升 2-3 倍，纹理流动幅度加大
- CSS `blur` 降低、`saturation` 提升、`opacity` 提高，让形态更清晰
- blob 边界加入有机形变（正弦叠加多边形），活跃时形变更强
- 微纹理流动线透明度提高、偏移量加大

### 26.3 AI 结束后

- 通过 `energy` 缓动慢慢扩散回原位，不突然熄灭

### 26.4 技术实现

| 层级 | 实现 |
|------|------|
| **全局状态** | `utils/aiActivity.ts` — axios 拦截器按 URL 模式识别 AI 请求，维护并发计数 |
| **状态广播** | `window.CustomEvent('zhishitong:ai-activity')` — 开放、解耦的事件通道 |
| **背景组件** | `AuroraBackground.tsx` — Canvas 动画，订阅 AI 活动事件，逐帧插值 `energy` |
| **CSS 联动** | `#aurora-canvas[data-ai-active]` — opacity/filter/transform 状态切换 |
| **初始化** | `main.tsx` 中调用 `setupAiActivityTracking()` 一次性安装 axios 拦截器 |

### 26.5 覆盖的 AI 调用路径

| 接口模式 | 触发场景 |
|---------|---------|
| `/api/ai/*` | 意图识别、合规分析、相似案例、审批意见生成、政策问答 Chatbot |
| `/api/ocr` | OCR / LLM OCR 文件识别 |
| `/api/approvals/suggest-review` | 审批智能建议 |
| `/api/approvals/manual` | 手动提交后触发的审批辅助引擎 |
| `/api/approvals/{id}/resubmit` | 撤回重提后触发的审批辅助引擎 |

并发安全：多个 AI 请求同时进行时保持活跃态，最后一个请求结束才回落。

---

## 二十七、前端架构设计

> **设计原则：** 前端采用 React 18 + TypeScript 构建，基于 iOS 原生设计语言实现了完整的玻璃拟态（Glassmorphism）设计系统。所有页面共享统一的视觉风格、动效规范和交互模式。

### 27.1 技术栈

| 依赖 | 版本 | 职责 |
|------|------|------|
| React | 18.3 | UI 框架（函数式组件 + Hooks） |
| TypeScript | 5.5 | 类型安全 |
| Vite | 5.4 | 构建工具 + 开发服务器 |
| React Router | 6.26 | 客户端路由（19 条路由） |
| Ant Design | 5.20 | ConfigProvider/中文 locale/主题 token 基础能力（业务 UI 主要为自研玻璃拟态组件） |
| Axios | 1.7 | HTTP 请求 + AI 活动拦截器 |

### 27.2 设计系统（Glass Design System）

#### CSS 变量体系

所有颜色、间距、圆角均通过 CSS 变量管理，深色模式通过 `@media (prefers-color-scheme: dark)` 自动切换：

```css
:root {
  --glass-bg: rgba(255, 255, 255, 0.65);      /* 玻璃卡片背景 */
  --glass-bg-strong: rgba(255, 255, 255, 0.82); /* 强调卡片 */
  --glass-border: rgba(255, 255, 255, 0.5);     /* 玻璃边框 */
  --radius: 22px;                                /* 大圆角 */
  --radius-sm: 12px;                             /* 小圆角 */
  --accent: #007aff;                             /* iOS 蓝 */
  --green: #34c759;                              /* 成功色 */
  --red: #ff3b30;                                /* 错误色 */
  --sidebar-width: 240px;                        /* 侧边栏宽度 */
  --font-stack: -apple-system, 'SF Pro Display', ...;
}
```

#### 玻璃卡片（`.glass-card`）

所有页面内容均包裹在玻璃卡片中：

- `backdrop-filter: blur(25px) saturate(180%)` — 毛玻璃效果
- `border-radius: 22px` — iOS 风格大圆角
- 统一圆角、半透明边框、阴影和 `overflow: hidden` 圆角遮罩
- 支持 `strong` 和 `size` 变体，交互动画主要由按钮、表格行、弹窗等具体组件承担

#### 深色模式

通过 CSS 变量自动切换，无需 JS 干预：

- 背景色：`#f2f2f7` → `#000000`
- 玻璃卡片：透明度降低（0.65 → 0.6）
- 文字：`#1d1d1f` → `#f5f5f7`
- 强调色：`#007aff` → `#0a84ff`

### 27.3 组件架构

#### Frame.tsx（569 行）— 布局框架

- **玻璃侧边栏**：固定左侧 240px，毛玻璃背景 + 导航高亮动画
- **角色导航**：根据用户角色动态渲染不同导航组
  - 普通用户：19 类申请入口 + 工具 + 社区
  - 管理员：模拟测试、API Key、学校管理、成员管理、系统监控、数据管理
  - 部门管理员：部门事务 + 数据看板
  - 学校管理员：全校事务 + 数据看板
  - 财务管理员：财务审批
- **模拟身份横幅**：管理员切换身份时顶部黄色提示条

#### AIChatPanel.tsx（385 行）— AI 政策问答

- 右下角悬浮圆形按钮（AI 图标）
- 点击展开聊天面板，支持多轮对话
- 消息气泡区分用户/AI，AI 消息支持 Markdown 渲染
- 引用来源显示（链接到政策知识库）

#### AIDecisionPanel.tsx（347 行）— AI 审批决策辅助

- 管理员审批页面的辅助面板
- 四个模块：合规分析、相似案例、政策条文、缺失信息
- 始终可见（不折叠），数据在审批详情加载时自动获取

#### AuroraBackground.tsx（252 行）— 全屏动态背景

- 6 个大型半透明 gradient blob 组成低饱和流体智能场
- blob 采用低频正弦叠加漂移，边界轻微有机形变
- AI 调用时：blob 向中上部隐形焦点聚合、速度提升、纹理流动增强
- 静态时：极低存在感，不抢卡片注意力

#### GlassCard.tsx（38 行）— 基础卡片

- 统一封装玻璃卡片样式
- 支持 `size` 属性控制内边距（xs/sm/md）
- 支持 `strong` 属性控制玻璃强度

#### AuthImage.tsx（73 行）— 认证图片

- 通过 axios blob 加载需要 JWT 认证的图片
- 解决 `<img src>` 无法携带 Authorization header 的 403 问题

### 27.4 页面路由（19 条）

```
/login                              → LoginPage（登录）
/                                   → WorkbenchPage（智能 OCR 工作台）
/apply/:docType                     → ManualFormPage（19 类申请表单）
/history                            → HistoryPage（我的事务）
/profile                            → ProfilePage（个人信息）
/dashboard                          → DashboardPage（数据看板）
/notifications                      → NotificationsPage（通知中心）
/announcements                      → AnnouncementsPage（公告制度）
/resources                          → ResourceBookingPage（资源预约）
/dept                               → DeptAdminPage（部门审批）
/finance                            → FinanceAdminPage（财务审批）
/school                             → SchoolAdminPage（学校管理）
/school/affairs                     → SchoolAffairsPage（全校事务）
/admin/test                         → AdminTestPage（模拟测试）
/admin/api-keys                     → AdminApiKeysPage（API Key 池）
/admin/schools                      → AdminSchoolsPage（学校管理）
/admin/members                      → AdminUsersPage（成员管理）
/admin/monitor                      → AdminMonitorPage（系统监控）
/admin/data                         → AdminDataPage（数据管理）
```

### 27.5 权限守卫

| 守卫组件 | 逻辑 |
|----------|------|
| `NeedAuth` | 未登录重定向 `/login` |
| `NeedAdmin` | 非信息管理员重定向 `/` |
| `NeedDeptStaff` | 非部门管理员重定向 `/` |
| `NeedFinanceStaff` | 非财务管理员重定向 `/` |
| `NeedSchoolStaff` | 非学校管理员重定向 `/` |
| `NeedStaff` | 任意管理员角色 |
| `NoFinanceAdmin` | 财务管理员禁止访问申请页面（角色分离） |
| `AdminRedirect` | 纯信息管理员访问 `/` 时重定向到管理页 |

### 27.6 Hooks & 工具

| Hook/工具 | 职责 |
|-----------|------|
| `useAuth` | JWT 认证状态管理（登录/登出/刷新用户信息） |
| `useFormStorage` | 表单数据本地暂存（防误刷新丢失） |
| `aiActivity.ts` | axios 拦截器，按 URL 模式识别 AI 请求，广播 CustomEvent |
| `api.ts` | API 错误解析与弹窗辅助函数 |
| `constants.ts` | 审批状态、阶段标签和前端兜底流程阶段常量 |

### 27.7 常量管理

| 文件 | 内容 |
|------|------|
| `docTypes.ts` | 19 类文档类型中文标签映射（`reimbursement` → `报销申请`） |
| `fieldLabels.ts` | 字段英文 key → 中文标签映射（`invoice_no` → `发票号码`） |
| `approvalStatus.ts` | 审批状态 → Emoji 映射（`pending` → `⏳`） |

---

## 二十八、待定/待讨论事项

> ⬜ 未决 | ✅ 已确认

| # | 状态 | 问题 | 决策 |
|---|:---:|------|------|
| 1 | ✅ | Free 层 OCR 方案 | EasyOCR 文字提取 + 本地小模型 JSON 填充（两阶段） |
| 2 | ✅ | 审批流程设计 | LangGraph 编排（见第五章） |
| 3 | ✅ | 模型预加载策略 | start.sh 轮询 + llama-cpp-python 进程启动即加载 |
| 4 | ✅ | API Key 加密 | Fernet 对称加密，密钥通过环境变量注入 |
| 5 | ✅ | JSON 动态模板渲染 | 后端 JSON Schema 定义，前端按 type 渲染 |
| 6 | ✅ | 文件上传安全 | MIME 白名单 + 魔数校验 + UUID 文件名 + 路径防逃逸；Docker `noexec` 卷为部署建议 |
| 7 | ✅ | 部署方式 | **本地开发**（start.sh 一键启动）+ Docker（未来规划） |
| 8 | ✅ | 本地模型 GGUF | 默认使用 Qwen3-14B LoRA GGUF，放在 models/ 目录；Qwen3-4B 作为跨平台备选 |
| 9 | ⬜ | EasyOCR 在 ARM 上的中文识别精度 | 后续需在 ARM Mac 上实际测试确认 |
| 10 | ✅ | 推理服务并发 | llama-cpp-python 支持并发请求排队（cont-batching），默认上下文 2048 tokens |
| 11 | ⬜ | 学校级套餐迁移 | 从用户级 tier 过渡到 school_config 表，见第十二章 |
| 12 | ⬜ | 日志链式防篡改 | SHA-256 链式校验，见第十四章 |
| 13 | ⬜ | 灰度发布机制 | 按学校灰度新模板/规则，见第十三章 |
| 14 | ⬜ | 文件扫描（AV/CDR） | 上传文件过沙箱/杀毒，见第八章待补充 |
| 15 | ✅ | 安装脚本策略 | 先预检再安装；已有依赖跳过；硬件不足时跳过模型/训练依赖并输出原因 |

---

## 二十九、变更摘要

| 版本 | 变更内容 |
|------|---------|
| v1.0 → v2.0 | 用户分层体系；API Key 池；软删除；4 面板管理后台 |
| **v2.0 → v3.0** | Free 层改为 EasyOCR 提取 + 本地小模型 JSON 填充（两阶段）；LangGraph 审批流程；AES Fernet 密钥存储；JSON 动态模板渲染；文件上传安全；单/多容器架构 |
| **v3.0 → v4.0** | 新增学校管理员角色；审批引擎改为「AI 辅助，不自动结论」；文档类型前端汉化；请假单固定字段；学校字段 tenant 化 |
| **v4.0 → v4.1** | 角色体系：去掉旧称「超级管理员」，改为「信息管理员」（API Key/数据/监控，不参与审批和用户管理）；新增第十二章「学校租户模型」：学校级套餐、租户隔离、学校管理员边界；新增第十三章「流程版本治理」：版本号规范、实例迁移策略、回滚与灰度；新增第十四章「审计合规与日志治理」：审计分层、日志防篡改、留存期限、数据脱敏、取证流程 |
| **v0.5.0 → v0.5.1** | UI 精进 — 全局按钮系统重构（圆角10px、弹簧动画、focus-visible无障碍、success/danger/lg变体）；侧边栏呼吸感增强（导航项14px、间距加大、宽240px）；折叠展开双向弹簧动画（grid-template-rows过渡）；弹窗入场/退场动画（modalFadeIn/Out + modalCardIn/Out）；AuthImage组件解决认证图片403问题；字段中文汉化补全（getFieldLabel统一映射）；审批面板UI统一（查看详情→弹窗审批）；AI填写意见按钮去重；合规分析面板始终可见；按钮emoji精简 |
| **v0.5.1 → v0.5.2** | 背景动画重构 — 从传统极光色带改为低饱和流体智能场（blob field + 有机形变 + 微纹理流动）；新增 AI 活动状态联动（axios 拦截器 → CustomEvent → Canvas 逐帧插值 energy）；AI 调用中背景聚合/加速/清晰化，结束后缓动回落；去掉扫光/粒子/HUD/环等廉价特效；颜色收敛为蓝、青、紫、暖白 |
| **v0.5.2 → v0.6.0** | 用户偏好持久化（收藏夹路径跨设备同步）；全新通知中心（批量已读/筛选/红点角标轮询）；历史记录翻新（多条件筛选/CSV 导出/撤回重新编辑）；工作台增强（NL 意图识别/批量上传/多会话暂存）；审批意见模板 & 代理委托；AI 感知动效增强（微纹理流动线）；CSS 设计系统完善（按钮变体/状态徽章/loading 动画/无障碍）；CSV 导出；审批流程健壮性（异常分类/撤回重提）；侧边栏导航重构（响应式折叠/角色分区）；后端基础设施增强 |
| **v0.6.0 → v0.6.1** | 成员管理全面升级（管理端编辑/硬删除/全字段表单）；监控面板重构（状态横幅/分布图/日志错误Tab筛选）；启动脚本优化（Redis 检测/训练依赖/模型验证/依赖缓存）；安全加固（`.jwt_secret` 持久化/JWT 刷新加固/登录限流）；登录页动画打磨；`.gitignore` 完善；配置中心化（JWT 过期时间/环境/允许源） |
| **v0.6.1 → v0.6.2** | 学生端手动填表提交前 RAG 合规自查（`/api/ai/manual-compliance`，不创建审批记录、不触发智能审批）；手动表单页新增蓝色合规自查按钮与风险/建议/引用政策展示；OCR 图片预处理加速（EXIF 修正、最大边 1800px、JPEG 85、扫描 PDF 转图后压缩）；多模态 OCR 使用压缩后 `image/jpeg` data URI；保留多模态 `max_tokens` 以避免 reasoning JSON 截断；新增跨平台安装脚本（预检、按需安装、VRAM 检测、模型下载进度条、安装报告）；新增后端测试覆盖 |
| **v0.6.2 → v0.6.2v2** | 智能指令填表接入当前登录账号上下文（第一人称自动补 applicant/student_id 等字段，帮别人填不冒充）；意图识别改为 LLM 自由输出 JSON + 后端字段归一化（`_normalize_json_keys`），不再发送全部模板定义；新增金额/类别正则兜底提取（`_intent_regex_fill`，"公务餐饮"映射为会议费）；NLP 识别与合规分析分步显示；AI 输出全局多色渐变样式（`ai-generated-panel`）；深色模式 AI 容器文字实体白色；AI 面板入场动画、引用条款折叠过渡、NLP 触发背景 blobs；修复政策小助手聊天气泡可读性；后端测试扩展至 16 个 |
| **v0.6.2v2 → v0.6.3** | 云端 LLM 负责自然语言填表，本地 Qwen3-14B LoRA GGUF 负责 RAG 合规分析/分类兜底；新增请假相对日期、地点、交通、公假类型规则补全；前端表单日期统一规范化为 `datetime-local` 可显示值；通知中心支持服务端类型过滤、分页和免刷新自动更新，侧边栏未读红点同步轮询刷新；资源预约补齐会议室/车辆管理和后端校验；审批详情自动触发 AI 合规分析并高亮推荐操作；政策助手和知识库更新至 2025 版；新增 MLX 多任务语料、14B LoRA 训练/融合/GGUF 转换管线；`.gitignore` 排除本地模型与训练产物 |
