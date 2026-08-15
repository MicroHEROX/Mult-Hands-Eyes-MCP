# 工程文档（Engineering）

工程结构、MCP 工具契约、命令与测试分层。API 细节见 [api.md](api.md)，术语见 [glossary.md](glossary.md)，坑与解法见 [solutions.md](solutions.md)。

## 1. 目标与设计原则

Multhands MCP 是**平台无关**的 MCP 服务器：让在线大模型（主对话模型）把重复、耗 token 的简单劳动（文本 + 视觉）交给**用户显式配置的**本地 OpenAI 兼容推理服务。

设计原则（不可违反）：

1. **纯客户端**：只发 HTTP 请求；绝不启动/停止进程、绝不写文件、绝不改环境变量。
2. **显式配置**：后端由用户填写（JSON 配置或环境变量）；不扫描端口、不自动探测。
3. **在线模型始终是主模型**：本地模型只能经工具触达，不替换 provider、不用流式。
4. **平台无关**：不依赖任何客户端；stdio 为默认传输，SSE / Streamable HTTP 可选。
5. **MCP 严格合规**：错误走协议级 `CallToolResult.isError=true`；成功结果为 JSON 文本内容（+ 可选 structuredContent）。

## 2. 模块结构与职责

```
src/multhands/
├── __init__.py    # __version__ = "0.1.0"
├── __main__.py    # python -m multhands 入口（转发到 server.main）
├── server.py      # MCP 服务器本体：MCPServer 实例、三个工具、CLI（parse_args/main）
├── config.py      # 配置层：Backend / Config / ConfigSource / 文件与环境变量解析、后端选择
├── client.py      # OpenAI 兼容客户端：chat_completion / probe / LocalError / 错误映射
├── images.py      # 图片摄入：路径 / data: / http(s) → data URL
├── prompts.py     # 视觉模板：analyze / ocr / compare + fidelity 规则
└── errors.py      # LocalCallError：工具对外抛出的错误类型（协议级 isError 的载体）
```

依赖方向（单向，无环）：

```
server.py ──► config.py ──► (标准库)
    │  ├────► client.py ──► config.py(Backend)
    │  ├────► images.py ──► (httpx)
    │  ├────► prompts.py
    │  └────► errors.py
```

- `config.py` 是唯一知道配置语义的模块，不发网络请求。
- `client.py` / `images.py` 是纯网络层，不知道 MCP。
- `server.py` 把三者粘合为 MCP 工具，并把 `ConfigError` / `LocalError` / `ImageError` 归一化为 `LocalCallError`。

## 3. MCP 工具契约

### 3.1 注册方式

- 使用 `mcp.server.mcpserver.MCPServer`（**要求 mcp ≥ 2.0.0**；1.x 的 `FastMCP` 已不存在）。
- 工具经 `@mcp.tool(description=...)` 注册；**参数描述必须**用 `Annotated[类型, Field(description="...")]` 声明——SDK 2.0 不再从 docstring 解析参数描述（[solutions.md §1.1](solutions.md#11-mcp-sdk-20-的-api-变化)）。
- 工具描述放进 `LOCAL_*_DESCRIPTION` 常量经 `description=` 传入（docstring 拼表达式不是合法 docstring，[solutions.md §1.2](solutions.md#12-docstring-拼接表达式不生效)）。

### 3.2 返回值契约

| 情形 | 工具函数行为 | 线上（wire）结果 |
| --- | --- | --- |
| 成功 | 返回 `dict`（JSON 可序列化） | `CallToolResult`：text content（JSON 文本）+ 可选 structuredContent，`isError=false` |
| 失败 | **抛出** `LocalCallError`（带稳定 code） | `CallToolResult.isError=true`，消息形如 `[CODE] message\nHint: ...` |

**禁止**把 `"isError": true` 藏进成功结果的 JSON 里——那是数据字段，不是协议语义（[solutions.md §1.3](solutions.md#13-错误必须走协议级-iserror)）。

### 3.3 工具清单

| 工具 | 能力 | 关键参数 |
| --- | --- | --- |
| `local_run` | 本地文本模型单次推理 | `prompt`（必填）、`system`、`backend`、`temperature`、`max_tokens`、`stop` |
| `local_vision` | 本地多模态模型识图/OCR/对比 | `mode`、`prompt`、`image_paths`、`image_urls`、`backend`、采样参数 |
| `local_status` | 列出配置后端 + 健康探测 | 无参数 |

完整参数与返回结构见 [api.md §3](api.md#3-工具tools)。

### 3.4 后端选择规则

由 `Config.get(name, capability)` 实现，权威定义见 [api.md §2.3](api.md#23-后端选择规则)。

## 4. 数据流

```
MCP 客户端（opencode / Claude Desktop / ...）
   │ stdio / SSE / Streamable HTTP（JSON-RPC 2.0）
   ▼
server.py 工具
   │ ConfigSource.get()  —— 每次调用重读配置（热重载，solutions.md §2.1）
   │ Config.get(name, capability)
   ▼
client.py chat_completion ──POST {baseURL}/v1/chat/completions──► 本地服务（KoboldCpp/Unsloth/llama.cpp/...）
   ▲                                                              │
   └──（非流式 JSON 响应：text / reasoning_content / usage / model）
```

视觉路径：`local_vision` → [images.py] 路径/URL → `data:image/...;base64` → 作为标准多模态 `content` 数组部分随请求发出。

## 5. 命令

| 命令 | 用途 |
| --- | --- |
| `uv sync --extra dev` | 安装依赖（含测试依赖） |
| `uv run multhands` | 启动服务器（默认 stdio） |
| `uv run pytest` | 全部测试（81 个） |
| `uv tool install .` / `uv tool uninstall multhands-mcp` | 安装/卸载独立工具 |

传输选项（`--transport` / `--host` / `--port`）权威定义见 [api.md §5](api.md#5-cli)。

## 6. 测试分层

| 层 | 文件 | 覆盖 | 网络 |
| --- | --- | --- | --- |
| 单元 | `test_prompts / test_images / test_config / test_client` | 模板、图片来源、配置解析、错误映射 | 无（MockTransport） |
| 集成 | `test_integration` | 进程内 HTTP 假后端上的 wire 格式（仅标准字段断言、多模态 content、compare 多图） | 进程内 HTTP |
| 工具级 | `test_server` | 三个工具直接调用、协议层结果形态、错误码 | 进程内 HTTP |
| 传输 | `test_transports` | stdio 旧协议版本协商、Streamable HTTP 原始握手（会话 ID、Accept 双类型） | 子进程 + ASGI |
| 行为/e2e | `test_e2e` | **官方 MCP 客户端** × stdio / Streamable HTTP 全流程 + 真实 Unsloth 错误路径（环境无 Unsloth 自动跳过） | 子进程 + 进程内 HTTP |

新增测试指引：

- 改 wire 格式 → `test_integration`（断言请求体只含标准字段）。
- 改工具行为 → `test_server`（直接调用工具函数），必要时补 `test_e2e`（官方客户端视角）。
- 改传输/协议行为 → `test_transports` + `test_e2e`。
- 真机环境相关 → `test_e2e`，用 `pytest.mark.skipif` 自适应环境。

## 7. 版本与兼容性

| 组件 | 版本 |
| --- | --- |
| 本项目 | `0.1.0`（`multhands.__version__`） |
| Python | ≥ 3.10（开发环境 3.12） |
| MCP Python SDK | `mcp>=2.0.0`（代码依赖 `mcp.server.mcpserver`，1.x 不兼容） |
| HTTP 客户端 | `httpx>=0.27.0` |

已验证的 MCP 协议版本：2024-11-05 / 2025-03-26 / 2025-06-18 / 2025-11-25。