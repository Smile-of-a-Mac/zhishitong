# 智审通 — 高校行政审批自动化 Agent

**🏆 竞赛项目说明** 
>本作品为参赛作品，选题来源于比赛文件中的赛题要求，不适用于生产环境。

高校行政审批自动化平台，支持多学校、多角色协同审批，集成智能 OCR（多模态 LLM 一步到位 + EasyOCR 降级 + PDF 文本提取）、LLM 驱动的表单填写与字段映射归一化、RAG 政策检索（TF-IDF）、LoRA 微调问答、Redis 缓存与限流、可视化数据看板。

---

## 项目结构

```
sito/
├── zhishitong/                         # 主应用
│   ├── backend/                        # Python 后端（FastAPI）
│   │   ├── main.py                     # 应用入口 & 中间件
│   │   ├── config.py                   # 全局配置（JWT、DB、LLM 等）
│   │   ├── database.py                 # SQLAlchemy 引擎 & Session
│   │   ├── seed.py                     # 种子数据（2 校 × 全角色）
│   │   ├── auth.py                     # JWT 认证 + 模拟身份覆盖
│   │   ├── models.py                   # SQLAlchemy 数据模型（15 张表）
│   │   ├── schemas.py                  # Pydantic 请求/响应模型
│   │   ├── templates.json              # 审批模板 Schema（19 类）
│   │   ├── data/policy_kb.json         # RAG 政策知识库
│   │   ├── routers/                    # API 路由（14 个模块）
│   │   │   ├── auth_router.py          #   注册/登录/个人信息/模拟身份
│   │   │   ├── ocr_router.py           #   图片上传 & 多级 OCR
│   │   │   ├── approval_router.py      #   审批提交/查询/催办/多阶段流转
│   │   │   ├── admin_router.py         #   用户管理/成员管理/API Key/模拟测试
│   │   │   ├── dept_router.py          #   部门审批队列
│   │   │   ├── finance_router.py       #   财务审批队列
│   │   │   ├── school_router.py        #   学校审批 & 事务总览
│   │   │   ├── monitor_router.py       #   系统监控（概览/日志/错误）
│   │   │   ├── dashboard_router.py     #   数据看板（按角色）
│   │   │   ├── notification_router.py  #   站内信通知
│   │   │   ├── announcement_router.py  #   公告 & 制度文库
│   │   │   ├── resource_router.py      #   资源预约（会议室+车辆）
│   │   │   ├── rag_router.py           #   AI 增强（意图/合规/案例/建议/对话/搜索）
│   │   │   └── shared.py              #   公共查询辅助
│   │   └── services/                   # 业务逻辑层
│   │       ├── ocr_service.py          #   OCR 多级路由 + JSON 填充
│   │       ├── approval_service.py     #   审批引擎（LLM + 多阶段）
│   │       ├── workflow.py             #   19 种事务的多阶段审批流程定义
│   │       ├── rule_engine.py          #   智能预审规则引擎
│   │       ├── rag_service.py          #   RAG + TF-IDF 知识库检索
│   │       ├── notification_service.py #   站内信推送
│   │       ├── key_pool.py             #   智能 API Key 池（多 Key 轮询+故障转移）
│   │       ├── redis_service.py        #   Redis 缓存 + 限流 + Key 池原子计数
│   │       ├── crypto_service.py       #   Fernet 加密
│   │       ├── file_service.py         #   文件校验/存储/清理
│   │       ├── template_service.py     #   模板加载 & 文档类型检测
│   │       └── logging_service.py      #   结构化日志
│   ├── frontend/                       # React 18 + TypeScript + Vite
│   │   └── src/
│   │       ├── App.tsx                 #   路由定义（19 个路由）
│   │       ├── main.tsx                #   入口
│   │       ├── components/             #   通用组件
│   │       │   ├── Frame.tsx           #     玻璃侧边栏 + 角色导航 + 模拟横幅
│   │       │   ├── GlassCard.tsx       #     毛玻璃卡片基础组件
│   │       │   ├── AuroraBackground.tsx #    低饱和流体智能场 Canvas
│   │       │   ├── AIChatPanel.tsx     #     右下角 AI 政策问答悬浮面板
│   │       │   ├── AIDecisionPanel.tsx #     AI 审批决策辅助面板（合规分析+相似案例）
│   │       │   ├── AuthImage.tsx       #     认证图片加载（axios blob）
│   │       │   └── ApprovalProgressBar.tsx # 多阶段审批进度条
│   │       ├── pages/                  #   页面
│   │       │   ├── auth/LoginPage.tsx            # 登录（演示账号收起动画）
│   │       │   ├── workbench/
│   │       │   │   ├── WorkbenchPage.tsx         # 智能 OCR 工作台
│   │       │   │   ├── ManualFormPage.tsx        # 手动填表
│   │       │   │   ├── DashboardPage.tsx         # 数据看板
│   │       │   │   ├── NotificationsPage.tsx     # 通知中心
│   │       │   │   ├── AnnouncementsPage.tsx     # 公告 & 制度文库
│   │       │   │   └── ResourceBookingPage.tsx   # 资源预约
│   │       │   ├── history/HistoryPage.tsx       # 我的事务
│   │       │   ├── profile/ProfilePage.tsx       # 个人信息
│   │       │   ├── admin/
│   │       │   │   ├── AdminUsersPage.tsx        # 用户管理
│   │       │   │   ├── AdminSchoolsPage.tsx      # 学校管理
│   │       │   │   ├── AdminApiKeysPage.tsx      # API Key 池
│   │       │   │   ├── AdminDataPage.tsx         # 数据管理（软删除）
│   │       │   │   ├── AdminMonitorPage.tsx      # 系统监控
│   │       │   │   └── AdminTestPage.tsx         # 模拟测试面板
│   │       │   ├── dept/DeptAdminPage.tsx        # 部门审批
│   │       │   ├── finance/FinanceAdminPage.tsx  # 财务审批
│   │       │   └── school/
│   │       │       ├── SchoolAdminPage.tsx       # 学校管理
│   │       │       └── SchoolAffairsPage.tsx     # 全校事务总览
│   │       ├── hooks/
│   │       │   ├── useAuth.tsx         #   认证 Hook
│   │       │   └── useFormStorage.ts   #   表单本地暂存
│   │       └── constants/
│   │           ├── docTypes.ts         #   文档类型标签
│   │           └── fieldLabels.ts      #   字段中文标签映射
│   ├── inference_server/               # llama.cpp 本地推理服务
│   │   ├── server.py                   #   自动 GPU 检测 + OpenAI 兼容 API
│   │   └── requirements.txt
│   ├── uploads/                        # 上传文件存储（按 user_id 隔离）
│   ├── start.sh                        # 一键启动（自动检测微调模型）
│   └── shutdown.sh                     # 一键停止所有服务
├── training/                           # LoRA 微调管线（MLX + PEFT 备选）
│   ├── train_lora_mlx.py               #   训练 + 融合 + GGUF（Qwen3-14B）
│   ├── train_lora.py                   #   PEFT 训练备选（Windows/CUDA/CPU）
│   └── merge_lora.py                   #   PEFT 合并备选
├── lora_output_mlx/                    # MLX 训练产出（本地生成，不提交）
├── models/                             # 模型文件
│   ├── Qwen3-14B/                      #   MLX 基座模型（~7.8GB）
│   └── qwen3-14b-lora.gguf            #   微调后 GGUF（~28GB）
├── data/                               # 训练数据 & 语料
│   ├── sdust_classification.jsonl      #   分类语料（100 条，10 类）
│   ├── build_classification_corpus.py  #   分类语料构建脚本
└── docs/
    ├── DESIGN.md                       #   产品设计文档（29 章）
    └── TROUBLESHOOTING.md              #   运维排查手册
```

---

## 前端架构

前端采用 **React 18 + TypeScript + Vite** 构建，基于 iOS 原生设计语言实现了完整的**玻璃拟态（Glassmorphism）设计系统**，代码集中在 `frontend/src` 下的组件、页面、Hooks、工具和样式模块中。

### 设计系统

| 特性 | 实现 |
|------|------|
| 🎨 **玻璃卡片** | `backdrop-filter: blur(25px) saturate(180%)`，圆角 22px，半透明边框，暗色模式自动适配 |
| 🌌 **全屏动态背景** | Canvas 绘制低饱和流体智能场（6 个大型 gradient blob + 微纹理流动），AI 调用时聚合、加速并略微清晰化 |
| 🌓 **深色模式** | `prefers-color-scheme: dark` 完整适配，CSS 变量一键切换 |
| 📱 **响应式** | 移动端侧边栏折叠 + 自适应布局 |
| 🎭 **动效系统** | 卡片触控缩放、弹窗入场/退场动画、按钮弹簧曲线（`cubic-bezier(0.34,1.56,0.64,1)`） |

### 核心组件

| 组件 | 行数 | 职责 |
|------|:----:|------|
| `Frame.tsx` | 569 | 玻璃侧边栏 + 角色导航（19 类申请入口 + 管理/审批面板） + 模拟身份横幅 |
| `AIChatPanel.tsx` | 386 | 右下角悬浮政策问答面板，支持多轮对话 + 来源引用 |
| `AIDecisionPanel.tsx` | 362 | AI 审批决策辅助：合规分析 + 相似案例 + 政策条文 + 缺失信息 |
| `AuroraBackground.tsx` | 252 | 全屏低饱和流体智能场，blob field + 有机形变 + 微纹理流动，AI 调用时联动 |
| `GlassCard.tsx` | 38 | 毛玻璃卡片基础组件（强弱样式、尺寸变体、统一圆角/阴影） |
| `ApprovalProgressBar.tsx` | 37 | 多阶段审批进度条（部门→财务→学校） |
| `AuthImage.tsx` | 73 | 认证图片加载（axios blob，解决 403 问题） |

### 页面路由（19 条）

| 分类 | 路由 | 权限 |
|------|------|------|
| **工作台** | `/` (OCR 智能工作台), `/dashboard`, `/notifications`, `/announcements`, `/resources` | 普通用户 |
| **申请** | `/apply/:docType` (19 类) | 普通用户 |
| **审批** | `/dept` (部门), `/finance` (财务), `/school` + `/school/affairs` (学校) | 对应管理员 |
| **管理** | `/admin/test`, `/admin/api-keys`, `/admin/schools`, `/admin/members`, `/admin/monitor`, `/admin/data` | 信息管理员 |
| **其他** | `/login`, `/profile`, `/history` | 全局 |

### 设计变量体系

```css
--glass-bg: rgba(255, 255, 255, 0.65);   /* 玻璃卡片背景 */
--glass-border: rgba(255, 255, 255, 0.5); /* 玻璃卡片边框 */
--radius: 22px;                            /* 卡片圆角 */
--accent: #007aff;                         /* 主强调色（iOS 蓝） */
--green: #34c759;                          /* 成功色 */
--red: #ff3b30;                            /* 错误色 */
--sidebar-width: 240px;                    /* 侧边栏宽度 */
--font-stack: -apple-system, 'SF Pro Display', ...; /* 系统字体栈 */
```

暗色模式下所有变量通过 `@media (prefers-color-scheme: dark)` 自动切换为深色系。

---

## 核心功能

### 🤖 审批流程
| 模块 | 功能 |
|------|------|
| 📄 **19 类审批模板** | 报销、请假、社团活动、教室借用、出差、用章、宿舍调换、奖学金、休学/复学、在读证明、因公出国、入职报到、办公用品领用、图书采购、成绩单打印、学历学位证明、试卷查阅、调停课、缓考补考 |
| 🔀 **多阶段审批** | 部门审批 → 财务审批 → 学校审批，支持金额阈值自动跳过 |
| 📊 **数据看板** | 按角色展示审批量、趋势、效率指标、部门排行 |
| 💬 **AI 辅助决策** | LLM 生成批语参考、政策条文引用、缺失信息标记、合规分析始终可见 |

### 🧠 AI 能力
| 模块 | 功能 |
|------|------|
| 📷 **智能 OCR** | 多模态 LLM 一步到位（Pro）→ 图片自动缩放压缩 → 字段名映射归一化 + 正则兜底提取 → EasyOCR 降级 + PDF 文本直接提取（pypdf） + 扫描件自动转图片（pymupdf） |
| 📚 **RAG 政策检索** | TF-IDF 向量检索 + LLM 生成，7 个 AI 端点，支持手动填表提交前合规自查 |
| 🎯 **意图识别** | 自然语言描述 → 云端 LLM 抽取表单字段，本地规则兜底补相对日期/地点/交通 |
| ⚖️ **合规性分析** | 本地 Qwen3-14B + RAG 检索相关政策条文，逐条核对申请合规性 |
| 🔍 **相似案例** | 检索历史审批记录，辅助审批人决策 |
| 💬 **政策问答 ChatBot** | 右下角悬浮面板，多轮对话 + 引用来源 |
| 📏 **预审规则引擎** | 硬性规则检查（必填/范围/查重），拦截不合规申请 |

### 🏫 学校 & 角色
| 模块 | 功能 |
|------|------|
| 🏫 **多学校管理** | 每校独立服务等级（Free/Pro），tenant 隔离 |
| 👥 **角色体系** | 信息管理员 → 学校管理员 → 部门管理员 → 财务管理员 → 普通用户 |
| 🔄 **模拟测试** | 管理员可临时切换身份测试系统，安全隔离不误写库 |
| 📢 **公告 & 制度文库** | 公告/政策/办事指南分类，置顶 + 阅读量统计 |

### 🔔 协作 & 资源
| 模块 | 功能 |
|------|------|
| 📬 **站内信通知** | 8 种通知类型 + 红点角标 + 分类筛选 + 服务端分页 + 快捷跳转 |
| 📋 **资源预约** | 会议室 + 公车预约，管理员维护资源，时间冲突检测 |
| 📝 **审批意见模板** | 预设常用批语，一键填入 |
| 🔄 **审批代理** | 审批人休假时可委托他人代为审批 |

### 🔐 安全 & 运维
| 模块 | 功能 |
|------|------|
| 🔑 **API Key 池** | 多 Key 加密存储、轮询、故障自动转移、Redis 原子计数 |
| 🛡️ **数据安全** | JWT + bcrypt + Fernet 加密 + 文件魔数校验 |
| 🗑️ **软删除** | 用户标记删除 → 管理员恢复/彻底删除 |
| 📋 **系统监控** | 概览/日志/错误 三面板 + 审计日志 |
| 🔍 **OCR 工具链追踪** | 监控日志显示 provider/model/tier/doc_type 完整调用链 |
| 🔗 **英文字段映射** | 多模态模型输出字段自动归一化为模板英文 key（invoice_number→invoice_no 等） |
| 🧪 **LoRA 微调** | 山科大实际流程数据 → MLX 微调 Qwen3-14B → 自动融合并输出 GGUF；PEFT 管线保留为跨平台备选 |

### 架构总览：Human-in-the-Loop

```
        ┌─ 👤 学生 ──────────────────────────────────────────────────┐
        │  上传文件 / NLP 描述                                       │
        │  ┌─ 🤖 AI Agent ─────────────────┐                       │
        │  │ OCR 提取 + JSON 填充          │                       │
        │  │ RAG 合规分析 (政策检索/风险判断)│                       │
        │  └──────────────┬────────────────┘                       │
        │                 ▼                                         │
        │  人工审查 → 修改 → 确认提交                               │
        └─────────────────┬─────────────────────────────────────────┘
                          ▼
        ┌─ 👤 审批人 ──────────────────────────────────────────────┐
        │  ┌─ 🤖 AI 辅助面板 ───────────────┐                     │
        │  │ 合规分析 / 相似案例 / 意见草稿   │                     │
        │  └──────────────┬────────────────┘                     │
        │                 ▼                                       │
        │ 人工决策 → 通过/驳回/需修改                             │
        └─────────────────┬─────────────────────────────────────────┘
                          ▼
        ┌─ 👤 学生 (被退回时) ──────────────────────────────────────┐
        │  修改后重提 → 回到审批流程                                 │
        └───────────────────────────────────────────────────────────┘
```

**设计原则：** AI 全程辅助，所有决策和行政责任保留给人类。详见 [docs/DESIGN.md](docs/DESIGN.md)「十五半、Human-in-the-Loop (HITL) 架构总览」。

---

## 技术栈

| 层 | 技术 |
|----|------|
| **前端** | React 18 + TypeScript + Vite + 玻璃拟态设计系统（Ant Design 5 目前用于 ConfigProvider/主题基础能力） |
| **后端** | FastAPI + SQLAlchemy + SQLite + LangGraph + Redis |
| **AI/OCR** | EasyOCR + 多模态 LLM API（MiMo/DeepSeek/Qwen-VL）+ 云端自然语言填表 + OCR 图片预处理（EXIF 修正、最大边 1800px、JPEG 85）+ llama.cpp 本地 Qwen3-14B 推理 + 字段名映射归一化 + 正则兜底提取 + pypdf 文本提取 + pymupdf 扫描件转图片 |
| **RAG** | TF-IDF (scikit-learn) + 自定义 JSON 知识库（policy_kb.json） |
| **LoRA** | MLX / mlx-lm（Apple Silicon，Qwen3-14B）+ PEFT / Transformers / PyTorch（Windows/CUDA/CPU 备选） |
| **缓存/限流** | Redis（OCR 缓存、Key 池原子计数、速率限制） |
| **安全** | JWT + bcrypt + Fernet + MIME 魔数校验 |
| **GPU 加速** | Metal (Apple Silicon) / CUDA (NVIDIA) / ROCm (AMD) / CPU 自动检测 |

---

## 快速开始

### 前提条件

- Python 3.11+, Node.js 18+
- 虚拟环境：`python -m venv .venv`

### 一键安装环境（v0.6.3）

安装脚本会先检查本机已有环境，已安装的依赖会跳过，不满足本地推理或 LoRA 训练条件时不会强行下载模型或训练依赖。

```bash
# macOS / Linux
bash setup/setup.sh
```

```powershell
# Windows PowerShell 5.1+ / PowerShell 7+
.\setup\setup.ps1
```

脚本会执行：Python/Node/Git 预检 → RAM/磁盘/GPU/VRAM/网络检测 → 创建 `.venv` → 按需安装后端、推理、训练和前端依赖 → 按条件下载跨平台 4B 备选模型 → 初始化数据库 → 输出安装报告。

模型下载由 `setup/_download_model.py` 负责，下载 Qwen3-4B GGUF 时会显示百分比、下载速度、已下载大小和总大小的进度条。若 HuggingFace 仓库需要认证，请先设置 `HF_TOKEN` 或 `HUGGINGFACE_TOKEN`。

硬件门槛：本地推理至少 4GB RAM；模型下载还需要 8GB 可用磁盘和 HuggingFace 网络连通；GPU LoRA 训练建议 8GB RAM + 6GB VRAM；纯 CPU LoRA 训练建议 12GB RAM。Windows 会通过 `nvidia-smi` 检测 NVIDIA VRAM，Apple Silicon 使用统一内存估算。

### 一键启动

```bash
cd zhishitong && bash start.sh
```

`start.sh` 自动完成：虚拟环境检测 → 依赖安装 → 数据库初始化 → 推理服务启动（含 GPU 检测） → 微调 GGUF 模型检测 → 后端启动 → 前端启动。

### 一键停止

```bash
cd zhishitong && bash shutdown.sh
```

`shutdown.sh` 按端口精确停止：推理服务 (18080) → 后端 (8080) → 前端 (5173)，并按进程名兜底清理。

### 手动启动

```bash
# 后端
cd zhishitong
source ../.venv/bin/activate
PYTHONPATH="$PWD/backend" uvicorn main:app --host 0.0.0.0 --port 8080 --reload

# 前端（新终端）
cd zhishitong/frontend && npm install && npx vite --host 0.0.0.0 --port 5173

# 本地推理服务（可选，新终端）
cd zhishitong && source ../.venv/bin/activate
PYTHONPATH="$PWD/inference_server" uvicorn server:app --host 0.0.0.0 --port 18080
```

### 种子数据

```bash
cd zhishitong
source ../.venv/bin/activate
PYTHONPATH="$PWD/backend" python backend/seed.py
```

### LoRA 微调（可选）

```bash
cd /Users/wangdaoyu/VSCode/sito
.venv/bin/python training/train_lora_mlx.py   # 训练 → 融合 → GGUF 一步完成
# start.sh 会自动检测 qwen3-14b-lora.gguf
```

---

## 演示账号

| 账号 | 密码 | 角色 | 学校 |
|------|------|------|------|
| `admin` | `admin123` | 信息管理员 | — |
| `sdu_school_admin` | `admin123` | 学校管理员 | 山东科技大学 |
| `sdu_dept_cs` | `123456` | 部门管理员（计算机学院） | 山东科技大学 |
| `sdu_dept_fin` | `123456` | 部门管理员（财务处） | 山东科技大学 |
| `sdu_finance_admin` | `admin123` | 财务管理员 | 山东科技大学 |
| `sdu_student_a` / `sdu_student_b` | `123456` | 学生 | 山东科技大学 |
| `sdujn_school_admin` | `admin123` | 学校管理员 | 山东科技大学（济南校区） |
| `sdujn_dept_cs` | `123456` | 部门管理员 | 山东科技大学（济南校区） |
| `sdujn_finance_admin` | `admin123` | 财务管理员 | 山东科技大学（济南校区） |
| `sdujn_student_a` / `sdujn_student_b` | `123456` | 学生 | 山东科技大学（济南校区） |

> 山东科技大学是 Pro 版（LLM OCR 30次/月），济南校区是 Free 版（仅本地 OCR）。
> 每校均有完整角色，格式 `{前缀}_{角色}`。

---

## 使用流程

| 角色 | 主要操作 |
|------|---------|
| 👨‍🎓 **学生** | 上传材料 → 自动填表 → 编辑确认 → 提交审批 → 查看进度 & 通知 |
| 🏢 **部门管理员** | 查看本部门待审队列 → 核实材料 → 查看 AI 合规分析/政策条文 → 通过/驳回/需修改 → AI 智能填写意见 |
| 💰 **财务管理员** | 查看报销待审 → 审核金额发票 → 财务通过/驳回 |
| 🏫 **学校管理员** | 管理部门管理员 → 查看全校事务总览 → 学校级审批 |
| 🔧 **信息管理员** | API Key 管理 → 创建/管理学校 → 用户管理 → 模拟测试 → 系统监控 → 数据看板 |

---

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `JWT_SECRET` | JWT 签名密钥 | 开发默认值 |
| `ENCRYPTION_KEY` | API Key Fernet 加密密钥 | 自动生成 |
| `LLAMA_SERVER_URL` | 本地推理服务地址 | `http://127.0.0.1:18080` |
| `MODEL_PATH` | 推理模型路径 | `models/qwen3-14b-lora.gguf` |
| `LLM_API_BASE` | 外部 LLM API 地址 | DashScope |
| `LLM_API_KEY` | 外部 LLM Key | 空（使用 Key 池） |
| `LLM_MODEL` | 多模态 OCR 模型 | `qwen-vl-max` |
| `LLM_FILL_MODEL` | JSON 填充默认模型 | `qwen-turbo` |
| `UPLOAD_DIR` | 上传目录 | `./uploads` |
| `MAX_FILE_SIZE_MB` | 文件大小上限 | `10` |

---

## 设计文档

- 📐 [产品设计文档（29 章）](docs/DESIGN.md) — 完整的产品架构、数据模型、审批流程、安全策略
- 🔧 [运维排查手册](docs/TROUBLESHOOTING.md) — 系统架构、常见问题排查、日志格式参考

---

## License

本项目代码采用 [Apache License 2.0](LICENSE) 开源。

说明：第三方依赖、外部 LLM API、Qwen 模型权重、EasyOCR 模型、数据源页面和比赛材料仍分别遵循其各自的许可证或服务条款；本许可证仅覆盖本仓库内由项目作者编写并提交的代码与文档。

---

## 最近更新 (v0.6.3)

- 🧠 **云端填表 + 本地合规分流**：自然语言表单预填强制使用云端 LLM，分类、RAG 合规分析和本地兜底继续使用 `models/qwen3-14b-lora.gguf`
- 🗓️ **请假相对日期补全**：后端规则兜底支持“明天/后天/明后两天”，并自动补全地点、交通工具和公假类型；前端统一把日期值规范化为 `datetime-local` 可显示格式
- 📬 **通知中心分页与自动更新**：通知 API 支持 `types` 服务端过滤，前端按分类分页显示；通知中心和侧边栏未读红点支持免刷新自动更新，避免 50 条截断后漏消息
- 📋 **资源预约增强**：补齐会议室/车辆管理入口、空状态、字段匹配和后端预约校验
- ⚖️ **审批 AI 体验增强**：审批详情打开后自动合规分析，并根据风险等级高亮推荐动作按钮
- 🏛️ **2025 版政策助手**：政策知识库和助手问题入口更新到 2025 年版
- 🧪 **Qwen3-14B MLX 微调管线**：新增多任务语料构建、MLX LoRA 训练/融合/GGUF 转换脚本，14B GGUF 成为本地推理默认模型
- 🧰 **发布卫生**：更新 `.gitignore`，排除本地模型、MLX 融合产物和训练拆分数据，避免误提交大文件

## 最近更新 (v0.6.2v2)

- 🧠 **智能指令填表接入账号上下文**：`/api/ai/intent` 把当前登录人姓名、学号、学院等账号信息传给 LLM，第一人称申请自动补 applicant/student_id 等基础字段；帮别人填写时以描述为准，不会用当前账号冒充
- 📄 **LLM 自由输出 + 后端字段归一化**：不再把模板字段定义塞进 prompt，让 LLM 自由判断事务类型并输出中英文混合 JSON，后端通过 `_normalize_json_keys` 统一映射，正则兜底提取金额和费用类别
- 🔒 **金额/类别正则兜底**：新增 `_intent_regex_fill`，当 LLM 未提取金额或未将"公务餐饮费"映射到合法 category 时自动补全（"公务餐饮"→会议费）
- ⚖️ **智能指令 + 合规分析分步显示**：工作台 NLP 识别后先展示预填结果、再独立触发合规分析，两项各自完成后分别显示
- 🎨 **AI 输出容器多色渐变**：全局 `ai-generated-panel` class（蓝/紫/绿/粉/黄低透明渐变），覆盖合规分析、智能建议、审批 AI 面板和聊天助手气泡
- 🌙 **深色模式文字实体化**：AI 容器和内联区域在深色模式下变实体白色，不再半透明发灰
- ✨ **动画与过渡增强**：AI 面板入场 cascade 动画；引用条款展开/关闭 grid 过渡动画；NLP 识别和合规分析触发背景 blobs 聚合动画
- ⚡ **OCR 图片预处理加速**：图片 OCR 前统一做 EXIF 方向修正、最大边缩放至 1800px、JPEG 85 压缩；扫描件 PDF 转图片后同样压缩
- 🧰 **跨平台安装脚本**：新增 `setup/setup.sh`、`setup/setup.ps1`、`setup/_download_model.py`，支持 macOS/Linux/Windows 预检、按需安装和安装报告
- 📊 **硬件能力检测**：安装前检查 RAM、磁盘、GPU/VRAM、网络；不满足本地推理或训练条件时跳过模型/训练依赖并说明原因
- ⬇️ **模型下载进度条**：Qwen3-4B GGUF 下载显示百分比、速度和大小，支持 `HF_TOKEN`/`HUGGINGFACE_TOKEN` 认证
- ⚖️ **学生端提交前合规自查**：手动填表页新增蓝色「提交前合规自查」按钮，调用 RAG 政策检索生成风险等级、逐项检查、建议和引用政策
- 🧠 **合规自查不触发审批**：新增 `/api/ai/manual-compliance`，只分析草稿字段，不创建审批记录、不运行智能审批流程
- 🧪 **测试覆盖**：新增手动合规接口测试、账号意图预填测试、正则兜底测试、OCR 图片预处理测试，后端测试扩展至 16 个

## 最近更新 (v0.6.1 & v0.6.0)

- 👥 **成员管理全面升级**：管理员端新增成员信息编辑（姓名/部门/学校/角色/状态）、硬删除功能，全字段表单支持
- 📊 **监控面板增强**：新增服务状态横幅、层级与状态分布图、日志/错误 Tab 分类筛选，`/api/health` 聚合状态
- ⚡ **启动脚本优化**：新增 Redis 可用性检测、训练依赖检查、模型存活性验证、依赖缓存机制
- 🔒 **安全加固**：`.jwt_secret` 自动生成与持久化、JWT 刷新令牌 Cookie HttpOnly 加固、登录失败率限制
- 🎨 **登录页面打磨**：演示账号展开/收起动画、滚动入场动效
- 📦 **.gitignore 完善**：新增 `.jwt_secret`、`.agent-skills/`、`.github/` 等规则
- 🔧 **配置中心化**：新增 `JWT_ACCESS_EXPIRE_MINUTES`、`JWT_REFRESH_EXPIRE_DAYS`、`APP_ENV`、`ALLOWED_ORIGINS` 环境变量
- 🖥️ **监控前端适配**：`AdminMonitorPage` 全面重构，实时状态标签 + 结构化日志展示

- ⭐ **用户偏好持久化**：新增侧边栏收藏夹功能，用户可收藏常用申请路径（`/apply/*`），数据持久化到后端，跨设备同步
- 📬 **通知中心**：全新通知管理页面 `/notifications`，支持批量已读、单条删除、按类型筛选、红点角标轮询
- 📋 **历史记录大升级**：`/history` 页面全面翻新——多条件筛选（文档类型/日期范围/状态）、CSV 导出、撤回后重新编辑提交
- 🏗️ **工作台增强**：Workbench 支持自然语言意图识别（NL→文档类型+预填字段）、批量上传队列处理、拖拽粘贴导入、多会话暂存防刷新丢失
- ✍️ **审批意见模板**：部门管理员可预设常用批语（通过/驳回/需修改），一键填入审批面板
- 🔄 **审批代理委托**：审批人可委托他人代为审批，支持时间段设置，到期自动失效
- 🧠 **AI 感知动效增强**：背景 blob 在 AI 调用时聚合/加速/清晰化，结束后缓动回落；新增微纹理流动线
- 🎨 **CSS 设计系统完善**：玻璃卡片强弱变体、按钮 success/danger/lg 变体、状态徽章/标签/表格统一样式、loading 纯 CSS 动画、`prefers-reduced-motion` 无障碍
- 🔍 **CSV 导出**：历史记录和审批列表支持 CSV 导出（UTF-8 BOM，Excel 友好）
- 🛡️ **审批流程健壮性**：撤回重提支持重新编辑表单数据；审批超时/参数错误异常分类处理；增强事务总览 API
- 📐 **侧边栏导航重构**：响应式折叠（移动端滑出抽屉）、角色专用导航分区、通知未读角标轮询
- 🔧 **后端基础设施**：新增 `user_preference_router`、增强 `dept_router` 过滤逻辑、模型 & Schema 扩展
