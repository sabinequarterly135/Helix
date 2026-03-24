> 🌐 [English](README.md) | [中文](README.zh-CN.md)

<p align="center">
  <img src="docs/logo.png" alt="Helix Logo" width="160" />
</p>

<h1 align="center">Helix</h1>

用自动化测试驱动的 LLM 提示词进化工具。给 Helix 一组测试用例，它会自动优化你的提示词——直到全部通过，同时确保已有功能不被破坏。

## Helix 是什么？

给定一个提示词模板和一组测试用例，Helix 会用遗传算法自动搜索最优的提示词。整个过程全自动：评估 → 选择 → 多轮 LLM 对话优化 → 变异 → 迭代。

多个独立种群（"岛屿"）并行进化，定期交换各自的优秀候选。每个岛屿内部，RCC 机制让一个 LLM 扮演"批评者"找出提示词的问题，再让另一个 LLM 扮演"作者"针对性地修改。玻尔兹曼选择确保在"用好的"和"试新的"之间保持平衡。

核心原则：**改了不能退步**。测试用例分关键、普通、低优先级三个层级，适应度函数对关键用例的退步惩罚极重。

Helix 自带 Web 界面，支持配置管理、进化过程的实时监控，以及运行后的详细分析（谱系树、提示词差异对比、变异效果统计等）。

## 主要特性

- **多岛并行进化**，自动迁移优秀候选 + 停滞重置
- **RCC 对话优化**：批评者找问题，作者改提示词，多轮迭代
- **段落级结构变异**，自动保留 `{{ 模板变量 }}`
- **分层回归测试**：关键 / 普通 / 低三个优先级
- **多 LLM 支持**：Gemini、OpenAI、OpenRouter、Anthropic 一键切换
- **实时监控**：WebSocket 推送进化过程到浏览器
- **交互式 Playground**：直接和优化后的提示词聊天测试
- **工具调用模拟**：LLM 自动生成 mock 响应
- **3D 可视化**：岛屿拓扑图、候选谱系树
- **多语言**：中文 / English / Español
- **一键部署**：Docker Compose

## 截图

| 模板与工具 | 进化结果 | 谱系树 |
|:---:|:---:|:---:|
| ![模板](docs/screenshots/template-tab.png) | ![运行详情](docs/screenshots/run-detail.png) | ![谱系](docs/screenshots/lineage.png) |
| 模板预览与格式化工具卡片 | 适应度曲线与岛屿拓扑 | 进化候选者的系谱树 |

### 运行分析 — 差异对比、谱系与测试结果

![运行分析](docs/screenshots/helix-run-analysis.gif)

## 快速开始

### 前置条件

- Python 3.13+
- Node.js 22+
- [uv](https://docs.astral.sh/uv/)（Python 包管理器）
- npm
- 至少一个 LLM 提供商的 API 密钥（Gemini、OpenAI、OpenRouter 或 Anthropic）

### 1. 克隆仓库

```bash
git clone https://github.com/Onebu/helix.git
cd helix
```

### 2. 配置环境

```bash
cp .env.example .env
```

编辑 `.env` 并设置你的 API 密钥：

```
GENE_GEMINI_API_KEY=your-key-here
```

所有可用选项请参见[环境变量参考](docs/SETUP.md#environment-variables-reference)。

### 3. 启动后端

```bash
uv sync
uv run uvicorn api.web.app:create_app --factory --host 127.0.0.1 --port 8000 --reload
```

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

### 5. 打开仪表板

在浏览器中导航至 [http://localhost:5173](http://localhost:5173)。

### 替代方案：Docker

使用 Docker 一键启动：

```bash
docker compose up --build
```

这将启动后端、前端（通过 nginx 在端口 80）和 SQLite 数据库。访问 [http://localhost](http://localhost) 使用仪表板。

## 架构概览

```
api/
  web/            FastAPI REST + WebSocket 端点
  config/         环境变量配置加载（Pydantic Settings）
  dataset/        测试用例管理
  evaluation/     适应度评分、采样、聚合
  evolution/      核心循环、岛屿、RCC、变异、选择
  gateway/        LLM 提供商注册、重试、成本追踪
  lineage/        候选者谱系追踪
  registry/       提示词注册和段落管理
  storage/        SQLAlchemy ORM（SQLite/PostgreSQL）

frontend/src/
  components/     React UI（shadcn/ui、Radix 基础组件）
  hooks/          useEvolutionSocket（WebSocket）、useChatStream（SSE）
  client/         从 OpenAPI 自动生成的 TypeScript API 客户端
  pages/          路由级页面组件
  i18n/           翻译文件（en、zh、es）
```

**后端**：FastAPI 工厂模式，SQLAlchemy 2.0 异步 ORM，pydantic-settings 配置级联，具有岛屿模型并行性的异步进化引擎。

**前端**：React 19 + Vite + TypeScript + Tailwind CSS v4 + shadcn/ui。Recharts 用于适应度图表，D3 用于系谱树，React Three Fiber 用于 3D 视图（延迟加载）。

**通信**：REST 用于 CRUD，WebSocket 用于实时进化事件，SSE 用于聊天游乐场流式传输。

详细架构文档请参见 [CLAUDE.md](CLAUDE.md)。

## 算法详情

<details>
<summary>进化流程</summary>

```
                    +-----------------------------+
                    |     评估种子提示词            |
                    |  (所有用例, 目标模型)          |
                    +--------------+--------------+
                                   |
                    +--------------v--------------+
                    |   克隆种子到 N 个岛屿         |
                    +--------------+--------------+
                                   |
              +--------------------v--------------------+
              |          每一代:                         |
              |  +----------------------------------+   |
              |  |  每个岛屿:                        |   |
              |  |    每次对话:                       |   |
              |  |      1. 玻尔兹曼父代选择           |   |
              |  |      2. RCC 批评者-作者循环        |   |
              |  |      3. 结构变异 (20%)             |   |
              |  |      4. 评估候选者                 |   |
              |  |      5. 更新种群                   |   |
              |  +--------------+-------------------+   |
              |                 |                        |
              |  +--------------v-------------------+   |
              |  |   循环迁移                         |   |
              |  |   岛屿 i -> 岛屿 (i+1) % N        |   |
              |  +--------------+-------------------+   |
              |                 |                        |
              |  +--------------v-------------------+   |
              |  |   岛屿重置 (每 K 代)               |   |
              |  |   最差岛屿 <- 全局最优             |   |
              |  +---------------------------------+   |
              +--------------------+--------------------+
                                   |
                    +--------------v--------------+
                    |    返回最佳候选者              |
                    +-----------------------------+
```

**玻尔兹曼选择** — Softmax 加权父代采样：`P(i) = exp((fitness_i - max) / T) / Z`。温度控制探索与利用的平衡。

**RCC（通过批判性对话进行优化）** — 多轮批评者-作者对话，元模型诊断失败然后用最小、针对性的编辑重写提示词。

**结构变异** — 段落级重组（重排、拆分、合并），带语法验证。以可配置概率应用（默认 20%）。

**多岛屿模型** — 并行子种群，循环迁移并定期重置停滞的岛屿。

</details>

### 适应度评估

| 预期输出 | 评分器 | 逻辑 |
|---------|--------|------|
| 仅 `tool_calls` | ExactMatchScorer | 名称 + 参数匹配 |
| 仅 `behavior` | BehaviorJudgeScorer | LLM 裁判逐条评估 |
| 两者都有 | 组合 | 先 ExactMatch，然后 BehaviorJudge |

分数按层级乘数聚合：关键 (5x)、普通 (1x)、低 (0.25x)。适应度为 0.0 表示所有用例通过。

### 配置参考

| 参数 | 默认值 | 描述 |
|------|--------|------|
| `generations` | 10 | 进化代数 |
| `n_islands` | 4 | 并行岛屿种群数 |
| `conversations_per_island` | 5 | 每岛每代 RCC 对话数 |
| `n_seq` | 3 | 每次对话的批评者-作者轮数 |
| `temperature` | 1.0 | 玻尔兹曼选择温度 |
| `pr_no_parents` | 1/6 | 从零生成的概率 |
| `structural_mutation_probability` | 0.2 | 每次对话结构变异概率 |
| `population_cap` | 10 | 每岛最大候选者数 |
| `budget_cap_usd` | None | 硬性预算上限 |

## 文档

- [安装指南](docs/SETUP.md) — 详细的安装、Docker 和部署说明
- [配置](docs/CONFIGURATION.md) — 环境变量、模型角色和设置界面
- [导入导出格式](docs/IMPORT_EXPORT.md) — 测试用例和角色的 JSON/YAML 格式
- [贡献指南](CONTRIBUTING.md) — 如何为 Helix 做贡献
- [架构](CLAUDE.md) — 详细的代码库文档和规范

## 技术栈

- **后端**：Python 3.13、FastAPI、Pydantic、SQLAlchemy（异步）、Jinja2
- **前端**：React 19、TypeScript、Vite、Tailwind CSS v4、shadcn/ui、Recharts、D3
- **LLM 提供商**：Google Gemini、OpenAI、OpenRouter、Anthropic（通过 AsyncOpenAI）
- **数据库**：SQLite（默认）或 PostgreSQL
- **部署**：Docker Compose、Vercel（前端）、Railway/Fly.io（后端）

## 参考文献

基于 [Mind Evolution: Evolutionary Optimization of LLM Prompts](https://arxiv.org/abs/2501.09891)（Google DeepMind, 2025）的思想。

## 许可证

MIT — 请参见 [LICENSE](LICENSE)。
