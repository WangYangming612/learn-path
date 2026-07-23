# LearnPath - 个性化学习路径动态生成系统

> **你只管学，剩下的交给我。**
>
> 一款面向自学者的 AI 学习助理——多计划管理 · 每日智能排期 · 反馈驱动的动态路径调整

---

## 技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| **后端框架** | FastAPI (0.115+) + Uvicorn (0.32+) | 异步 Web 框架 + ASGI 服务器 |
| **后端语言** | Python 3.11+ | 开发语言 |
| **依赖管理** | uv | Python 包管理与虚拟环境 |
| **ORM** | SQLAlchemy 2.x (asyncio) | 异步数据库 ORM |
| **API 文档** | FastAPI 自动生成 (Swagger / OpenAPI) | 接口文档与调试 |
| **前端框架** | React 18 + TypeScript 5 | UI 框架 |
| **构建工具** | Vite 6 | 前端开发与构建 |
| **UI 组件库** | Ant Design 5 | 企业级 UI 组件 |
| **状态管理** | Zustand 5 | 轻量状态管理 |
| **HTTP 客户端** | Axios | 前端 API 调用 |
| **AI 编排** | LangGraph 0.2+ / LangChain | 多智能体协同编排 |
| **开发数据库** | SQLite (aiosqlite) | 开发阶段数据存储 |
| **向量数据库** | ChromaDB | 画像语义检索与存储 |
| **缓存** | Redis | 缓存与任务队列 |

---

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 20 LTS+
- uv (Python 包管理器)
- npm (Node 包管理器)

### 后端启动

```bash
cd backend
uv run uvicorn app.main:app --reload
```

启动后访问:
- API: http://localhost:8000 → 返回 `{"status": "ok"}`
- 文档: http://localhost:8000/docs → Swagger UI

### 前端启动

```bash
cd frontend
npm install
npm run dev
```

启动后访问: http://localhost:5173

---

## 项目结构

```
learnpath/
├── backend/                 # 后端项目
│   ├── app/                 # 应用代码
│   │   ├── api/v1/          # API 路由
│   │   ├── agents/          # LangGraph 智能体
│   │   ├── core/            # 核心配置
│   │   ├── db/              # 数据库会话
│   │   ├── llm/prompts/     # LLM 调用与提示词
│   │   ├── models/          # SQLAlchemy ORM 模型
│   │   ├── schemas/         # Pydantic Schema
│   │   ├── utils/           # 工具函数
│   │   └── main.py          # 应用入口
│   ├── tests/               # 测试
│   ├── .env.example         # 环境变量模板
│   ├── config.yaml          # 应用配置
│   └── pyproject.toml       # 依赖管理
├── frontend/                # 前端项目
│   ├── src/                 # 源码
│   │   ├── components/      # 通用组件
│   │   ├── hooks/           # 自定义 Hooks
│   │   ├── pages/           # 页面组件
│   │   ├── services/        # API 调用
│   │   ├── stores/          # Zustand 状态
│   │   ├── types/           # TypeScript 类型
│   │   ├── App.tsx          # 根组件
│   │   └── main.tsx         # 入口
│   ├── index.html           # HTML 模板
│   ├── vite.config.ts       # Vite 配置
│   ├── tsconfig.json        # TypeScript 配置
│   └── package.json         # 依赖管理
├── docs/                    # 项目文档
├── .gitignore
└── README.md
```

---

## 开发环境要求

| 工具 | 最低版本 | 安装方式 |
|------|---------|---------|
| Python | 3.11+ | python.org 或包管理器 |
| Node.js | 20 LTS+ | nodejs.org 或包管理器 |
| uv | 最新版 | `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"` |
| Git | 2.x | git-scm.com |

---

## 开发流程

本项目按 17 步迭代开发，每步产出可运行可验证的 MVP。每步完成后执行 `git commit` 并打 tag。

```bash
# 查看所有步骤
git tag -l

# 回退到特定步骤
git checkout tags/step-1-init
```
