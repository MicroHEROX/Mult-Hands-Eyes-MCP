<div align="center">

# Mult Hands Eyes MCP

**给在线大模型一双本地的手——和一双本地的眼睛。**

[![version](https://img.shields.io/badge/version-0.1.0-blue)](https://github.com/MicroHEROX/Mult-Hands-Eyes-MCP/releases)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![python](https://img.shields.io/badge/python-%E2%89%A53.10-3776AB?logo=python)](https://python.org)
[![mcp](https://img.shields.io/badge/MCP-stdio%20%7C%20SSE%20%7C%20Streamable%20HTTP-8A2BE2)](https://modelcontextprotocol.io)
[![tests](https://img.shields.io/badge/tests-81%20passed-brightgreen)](docs/engineering.md)

**语言** &nbsp;|&nbsp; [**English**](README.md) &nbsp;•&nbsp; [**简体中文**](README.zh-CN.md)

</div>

一个**平台无关的 [MCP](https://modelcontextprotocol.io) 服务器**：让**在线大模型**（opencode、Claude Desktop、Cursor、Cline、Windsurf、Cherry Studio……）把重复、耗 token 的简单劳动交给本机运行的** OpenAI 兼容本地推理服务**——纯文本工作**和**视觉工作（识图 / OCR / 图片对比）。

主模型保持在你部署的位置不变。当任务在本地做更划算时，模型会调用：

- **`local_run`** — 在本地**文本**模型上跑一条提示词：批量改写、名字翻译、字符串处理、去重、短摘要、结构化提取。
- **`local_vision`** — 把图片交给本地**多模态**模型：OCR、图像分析、多图对比，使用结构化报告模板。纯文本的在线模型靠它获得眼睛：传图片路径或链接，拿回文本。
- **`local_status`** — 列出已配置后端并做健康探测。

本服务器是**纯客户端**：绝不启动、占有、杀死任何进程，绝不写任何文件；只对你**自己运行**的服务发 HTTP 请求。

---

## 做了哪些事

- 三个模型可见工具（`local_run` / `local_vision` / `local_status`），基于官方 MCP Python SDK（≥ 2.0）注册。
- **任意 OpenAI 兼容端点**：KoboldCpp、Unsloth Desktop、llama.cpp server、LM Studio、Ollama `/v1`、text-generation-webui——一份 JSON 配置声明多个后端，按 `text` / `vision` 能力路由。
- **结构化视觉报告**：`analyze`（8 段报告）、`ocr`（逐字提取）、`compare`（2–4 张图联合推理，5 段报告），附保真规则（逐字转发、不得编造、保留不确定性）。
- **三种图片来源**：本地文件路径、`data:` URL、`http(s)://` URL（由服务器下载转码，本地模型无需联网）。
- **三种传输**：stdio（默认，零参数启动）、SSE、Streamable HTTP——2024-11-05 / 2025-03-26 / 2025-06-18 / 2025-11-25 均已用官方 MCP 客户端实测。
- **配置热重载**：每次调用重读 JSON 配置，改完即生效；文件编辑到一半时沿用上次有效配置。
- **规范级错误**：所有失败都以协议级 `CallToolResult.isError=true` 呈现，带稳定 `[CODE]` 与可操作提示，模型可据此自愈。
- **两种安装方式**：`uv tool install .`（Python）或 `npx mult-hands-eyes-mcp`（npm 包装器，自带独立 venv 引导）。

## 没做哪些事

- **不替换**模型提供方——在线模型始终是主脑，本地模型只能经两个工具触达。
- **不启动、不配置、不停止**任何本地服务，不扫描端口、不自动探测；端点由你显式填写。
- **不捆绑、不托管**模型文件（GGUF / mmproj）。模型自备。
- **不用流式**——一次工具调用拿全量结果（更简单、够用）。
- **不改动**任何客户端配置文件——MCP 条目由你自己添加。

---

## 环境要求

| 项 | 要求 |
| --- | --- |
| Python | ≥ 3.10（npm 包装器会自动检查） |
| 本地服务 | 任一 OpenAI 兼容服务器，如 KoboldCpp（5001）、Unsloth Desktop（8888）、llama-server（8080）、LM Studio（1234）、Ollama（11434） |
| 视觉（可选） | 多模态模型**及其 mmproj** 投影器（KoboldCpp：`.kcpps` 里配 `"mmproj"`；llama-server：`--mmproj`；Unsloth：切换视觉模型） |

## 安装方式

```sh
git clone https://github.com/MicroHEROX/Mult-Hands-Eyes-MCP.git
cd Mult-Hands-Eyes-MCP
uv tool install .            # 隔离安装，不污染系统 Python
multhands --help
```

或从 npm（打包了同一个 Python 服务器；首次运行自动创建私有 venv 并安装两个小依赖）：

```sh
npx mult-hands-eyes-mcp
```

## 配置方式

任意位置建 `multhands.json`，用 `MULTHANDS_CONFIG` 指向它（未设置时回退到工作目录下的 `multhands.json`）：

```json
{
  "defaultBackend": "koboldcpp",
  "backends": {
    "koboldcpp": {
      "baseURL": "http://127.0.0.1:5001",
      "model": "koboldcpp",
      "capabilities": ["text", "vision"],
      "timeoutMs": 120000,
      "maxTokens": 8192
    },
    "unsloth": {
      "baseURL": "http://127.0.0.1:8888",
      "model": "unsloth",
      "apiKey": "sk-unsloth-xxxxxxxx",
      "capabilities": ["text", "vision"]
    }
  }
}
```

单后端快捷方式：`MULTHANDS_BASE_URL=http://127.0.0.1:5001`（可选 `MULTHANDS_MODEL`、`MULTHANDS_API_KEY`）。

| 字段 | 含义 |
| --- | --- |
| `baseURL` | 服务端点（必填） |
| `model` | 发给服务器的模型 id（KoboldCpp 等忽略它；默认同后端名） |
| `apiKey` | 需要鉴权的服务（Unsloth：Settings → API） |
| `capabilities` | `"text"` 和/或 `"vision"`，工具按能力选后端 |
| `timeoutMs` / `maxTokens` | 单次调用预算（默认 120000）/ 默认输出上限（默认 8192） |
| `defaultBackend` | 顶层字段：未指定时的缺省后端 |

## 使用方法

### `local_run` — 文本

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `prompt` | string | 是 | 指令/文本（user 消息） |
| `system` | string | 否 | 系统指令 |
| `backend` | string | 否 | 后端名；缺省用 `defaultBackend` |
| `temperature` | number | 否 | 0–2 |
| `max_tokens` | integer | 否 | 默认后端 `maxTokens` |
| `stop` | string[] | 否 | 停止序列 |

返回 `{ text, reasoning?, model, backend, usage, elapsed_ms }`。

### `local_vision` — OCR / 分析 / 对比

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `mode` | `analyze`/`ocr`/`compare` | 否 | 默认 `analyze` |
| `prompt` | string | 否 | 自定义指令（覆盖模板） |
| `image_paths` | string[] | 否 | 本地绝对路径（png/jpg/jpeg/webp/gif/bmp，单张 ≤ 20 MB） |
| `image_urls` | string[] | 否 | `data:` 或 `http(s)://` URL |
| `backend` | string | 否 | 后端名（须声明 `vision`） |
| `temperature` | number | 否 | OCR 建议 ~0.2 |
| `max_tokens` | integer | 否 | 输出上限 |
| `stop` | string[] | 否 | 停止序列 |

返回 `{ text, reasoning?, model, backend, images, usage, elapsed_ms }`。`compare` 一次请求 2–4 张图联合推理。

### `local_status` — 后端与健康

无参数。返回每个已配置后端的 `reachable`（实时 `GET /v1/models` 探测）与 `note`（AUTH 注释 = 服务在运行但 key 未通过）。

## 接入客户端

所有客户端同一前提：`multhands` 在 PATH 上（`uv tool install .`），配置经环境变量传入。

<details>
<summary><b>opencode</b> — <code>opencode.json</code></summary>

```json
{
  "mcp": {
    "multhands": {
      "type": "local",
      "command": ["multhands"],
      "enabled": true,
      "environment": { "MULTHANDS_CONFIG": "/path/to/multhands.json" }
    }
  }
}
```

</details>

<details>
<summary><b>Claude Desktop</b> — <code>claude_desktop_config.json</code></summary>

```json
{
  "mcpServers": {
    "multhands": {
      "command": "multhands",
      "env": { "MULTHANDS_CONFIG": "/path/to/multhands.json" }
    }
  }
}
```

</details>

<details>
<summary><b>Cursor</b> — <code>~/.cursor/mcp.json</code></summary>

```json
{
  "mcpServers": {
    "multhands": {
      "command": "multhands",
      "env": { "MULTHANDS_CONFIG": "/path/to/multhands.json" }
    }
  }
}
```

</details>

<details>
<summary><b>Cline</b> — <code>~/.cline_mcp_settings.json</code></summary>

```json
{
  "mcpServers": {
    "multhands": {
      "command": "multhands",
      "env": { "MULTHANDS_CONFIG": "/path/to/multhands.json" }
    }
  }
}
```

</details>

<details>
<summary><b>Windsurf</b> — <code>~/.codeium/windsurf/mcp_config.json</code></summary>

```json
{
  "mcpServers": {
    "multhands": {
      "command": "multhands",
      "env": { "MULTHANDS_CONFIG": "/path/to/multhands.json" }
    }
  }
}
```

</details>

<details>
<summary><b>Cherry Studio / Coco Chat / 图形客户端</b></summary>

添加 MCP 服务器，类型选 **Stdio**：命令 `multhands`，参数留空，环境变量 `MULTHANDS_CONFIG=<配置路径>`。

</details>

<details>
<summary><b>网络模式（Streamable HTTP / SSE）</b> — 远程或浏览器客户端</summary>

```sh
multhands --transport streamable-http --host 0.0.0.0 --port 8020   # 端点：http://<host>:8020/mcp
multhands --transport sse --host 0.0.0.0 --port 8021               # 端点：http://<host>:8021/sse
```

默认绑定 `127.0.0.1`，只有显式传 `--host 0.0.0.0` 才对外开放。

</details>

## 卸载删除

干净、零残留：

1. 从客户端配置里删除 `multhands` 条目（其他 MCP 条目不受影响）。
2. `uv tool uninstall multhands-mcp`（或 `npm uninstall -g mult-hands-eyes-mcp`）。
3. 删除克隆的文件夹。

运行时服务器不写任何文件，因此没有其他需要清理的东西。

## 文档

| 文档 | 内容 |
| --- | --- |
| [docs/engineering.md](docs/engineering.md) | 工程结构、工具契约、命令、测试分层 |
| [docs/api.md](docs/api.md) | 权威 API 参考（配置、工具、类、错误码、CLI、wire 契约） |
| [docs/glossary.md](docs/glossary.md) | 标准术语表 |
| [docs/solutions.md](docs/solutions.md) | 坑、疑难问题、解决方法、方法论 |

> 文档随仓库发布，但刻意**不打包进** pip/npm 安装包。

## 路线图

**可以走的方向：**

- 更多视觉模式与模板（文档版式、表格提取）。
- 批量任务：一个 agent 回合驱动多次本地调用。
- 可选的常用端口自动探测（当前刻意不做的显式配置）。
- 发布 Python 包到 PyPI（`uvx mult-hands-eyes-mcp`）。

**不能/不会走的方向：**

- 变成 LLM provider 适配器——在线模型始终是主脑。
- 管理进程——服务器保持纯客户端，你的服务归你管。
- 流式响应——一次往返拿全量结果更简单、够用。
- 捆绑模型文件（GGUF / mmproj）或修改任何本地服务。

## 致谢

- **[DeepSeek AI](https://github.com/deepseek-ai)** —— [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 平台及其插件模式塑造了本项目，经由参考插件 **[dsh-koboldcpp-hands](https://github.com/MicroHEROX/dsh-koboldcpp-hands)** 与 **[dsh-unsloth-hands](https://github.com/MicroHEROX/dsh-unsloth-hands)**（MIT）。
- **[LostRuins / KoboldCpp](https://github.com/LostRuins/koboldcpp)** 与 **[Unsloth](https://github.com/unslothai/unsloth)** —— 让这一切成为可能的本地推理服务。
- **[llama.cpp](https://github.com/ggml-org/llama.cpp)** 与 GGUF 量化生态。
- **[Model Context Protocol](https://modelcontextprotocol.io)** —— 协议及其 Python SDK。
- 运行在你机器上的开源模型们。

与 DeepSeek AI、LostRuins、Unsloth AI 无隶属关系；所有商标归其所有者。

## License

[MIT](LICENSE)
