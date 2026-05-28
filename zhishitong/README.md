# 智审通 — 高校行政审批自动化 Agent

高校行政审批自动化平台，支持多学校、多角色协同审批，集成智能 OCR 与 LLM 驱动的表单填写。

---

## 项目结构

```
zhishitong/
├── backend/                # Python 后端
│   ├── main.py             # FastAPI 入口
│   ├── config.py           # 全局配置（JWT、数据库、LLM等）
│   ├── database.py         # SQLAlchemy 引擎与 Session
│   ├── seed.py             # 种子数据初始化
│   ├── auth.py             # JWT 认证（hash、token、依赖注入）
│   ├── models.py           # SQLAlchemy 数据模型
│   ├── schemas.py          # Pydantic 请求/响应模型
│   ├── templates.json      # 审批表单模板
│   ├── routers/            # API 路由（按模块）
│   │   ├── auth_router.py       # 注册/登录/个人信息
│   │   ├── ocr_router.py        # 图片上传 & OCR 识别
│   │   ├── approval_router.py   # 审批提交/查询/智能建议
│   │   ├── admin_router.py      # 学校管理/成员管理/API Key
│   │   ├── dept_router.py       # 部门审批
│   │   ├── finance_router.py    # 财务审批
│   │   ├── school_router.py     # 学校审批
│   │   └── monitor_router.py    # 系统监控
│   └── services/           # 业务逻辑层
│       ├── ocr_service.py       # OCR 层（多级路由+JSON填充）
│       ├── approval_service.py  # LangGraph 审批引擎
│       ├── workflow.py          # 多阶段审批流程定义
│       ├── crypto_service.py    # Fernet 加密
│       ├── file_service.py      # 文件校验/存储/清理
│       ├── template_service.py  # 模板加载 & 文档类型检测
│       └── logging_service.py   # 结构化日志
├── frontend/               # React 前端
│   └── src/
│       ├── App.tsx              # 路由定义
│       ├── components/          # 通用组件
│       │   ├── Frame.tsx        # 玻璃侧边栏布局
│       │   └── GlassCard.tsx    # 毛玻璃卡片
│       ├── pages/               # 页面（按模块）
│       │   ├── auth/            # LoginPage
│       │   ├── workbench/       # WorkbenchPage, ManualFormPage
│       │   ├── history/         # HistoryPage
│       │   ├── profile/         # ProfilePage
│       │   ├── admin/           # API Keys, 学校管理, 成员管理, 监控
│       │   ├── dept/            # 部门审批
│       │   ├── finance/         # 财务审批
│       │   └── school/          # 学校管理 & 事务总览
│       ├── hooks/useAuth.tsx    # 认证 Hook
│       └── constants/           # 文档类型 & 字段标签
├── inference_server/       # llama.cpp 本地推理服务（可选）
├── data/                   # SQLite 数据库
├── uploads/                # 上传文件存储
└── start.sh                # 一键启动脚本
```

## 核心功能

| 模块 | 功能 |
|------|------|
| 🤖 **智能 OCR** | 上传图片/PDF → EasyOCR 文本提取 → LLM JSON 填充，多级降级 |
| 📝 **审批工作流** | 多阶段审批（部门 → 财务 → 学校），支持金额阈值跳过 |
| 🏫 **多学校管理** | 每校独立服务等级（Free/Pro），全员统一层级 |
| 👥 **角色体系** | 超级管理员 → 学校管理员 → 部门/财务管理员 → 学生 |
| 🔑 **API Key 池** | 加密存储多个 LLM Key，故障转移和配额管理 |
| 💡 **智能建议** | 审批时调用 LLM 生成批语参考 |

## 技术栈

- **前端**: React 18 + TypeScript + Vite
- **后端**: FastAPI + SQLAlchemy + SQLite + LangGraph
- **AI**: EasyOCR + 外部 LLM API（MiMo/DeepSeek）+ llama.cpp（可选本地）
- **安全**: JWT + bcrypt + Fernet 加密

## 快速开始

### 前提条件

- Python 3.11+, Node.js 18+
- 虚拟环境：`python -m venv .venv`

### 一键启动

```bash
cd zhishitong && bash start.sh
```

### 手动启动

```bash
# 后端
cd zhishitong
source ../.venv/bin/activate
PYTHONPATH="$PWD/backend" uvicorn main:app --host 0.0.0.0 --port 8080 --reload

# 前端（新终端）
cd zhishitong/frontend && npm install && npx vite --host 0.0.0.0 --port 5173
```

### 种子数据

```bash
PYTHONPATH="$PWD/backend" python backend/seed.py
```

## 演示账号

| 账号 | 密码 | 角色 | 学校 |
|------|------|------|------|
| admin | admin123 | 超级管理员 | — |
| sdu_school_admin | admin123 | 学校管理员 | 山东科技大学 |
| sdu_dept_cs | 123456 | 部门管理员 | 山东科技大学 |
| sdu_finance_admin | admin123 | 财务管理员 | 山东科技大学 |
| sdu_student_a | 123456 | 学生 | 山东科技大学 |
| sdujn_school_admin | admin123 | 学校管理员 | 山东科技大学（济南校区） |
| sdujn_student_a | 123456 | 学生 | 山东科技大学（济南校区） |

> 山东科技大学是 Pro 版（LLM OCR 30次/月），济南校区是 Free 版（仅本地 OCR）。
> 每校均有完整角色，格式 `{前缀}_{角色}`。

## 使用流程

| 角色 | 主要操作 |
|------|---------|
| 学生 | 上传材料 → 自动填表 → 提交审批 → 查看进度 |
| 部门管理员 | 查看本部门待审 → 核实材料 → 智能建议 → 通过/驳回 |
| 学校管理员 | 管理部门管理员 → 查看全校事务 → 学校级审批 |
| 财务管理员 | 查看报销待审 → 审核金额发票 → 财务通过 |
| 超级管理员 | API Key 管理 → 创建/管理学校 → 添加成员调整权限 → 系统监控 |

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `JWT_SECRET` | JWT 签名密钥 | 开发默认值 |
| `ENCRYPTION_KEY` | API Key 加密密钥 | 自动生成 |
| `LLAMA_SERVER_URL` | 本地推理服务 | `http://127.0.0.1:18080` |
| `LLM_API_BASE` | LLM API 地址 | DashScope |
| `LLM_API_KEY` | LLM Key | 空（使用池） |
| `UPLOAD_DIR` | 上传目录 | `./uploads` |
| `MAX_FILE_SIZE_MB` | 文件大小上限 | `10` |
