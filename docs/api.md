# API 参考（api.md）

Multhands MCP `0.1.0` 的权威 API 参考：配置、环境变量、工具、模块与类、错误码、CLI。

## 1. 配置（Config）

### 1.1 配置通道（按优先级）

| 通道 | 说明 |
| --- | --- |
| 1. JSON 配置文件 | `MULTHANDS_CONFIG` 指向的路径；未设置时回退当前工作目录的 `multhands.json` |
| 2. 环境变量 | 单后端快速通道（见 §1.3） |

### 1.2 JSON 配置文件格式

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
    }
  }
}
```

字段表：

| 字段 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `backends` | object | 必填 | 后端映射；键为后端名（任意非空字符串，供工具 `backend` 参数引用） |
| `backends.<name>.baseURL` | string | 必填 | 服务端点，如 `http://127.0.0.1:5001`（尾部 `/` 会被剥掉） |
| `backends.<name>.model` | string | 后端名 | 发给服务器的模型 id（KoboldCpp 等忽略它，照常服务已加载模型） |
| `backends.<name>.apiKey` | string | 无 | 需要鉴权的服务（Unsloth：Settings → API 创建）；有值即发 `Authorization: Bearer` |
| `backends.<name>.capabilities` | string[] | `["text","vision"]` | 该后端声明支持的能力；合法值仅 `text` / `vision` |
| `backends.<name>.timeoutMs` | integer | 120000 | 单次调用总预算（含图片下载）；必须为正整数 |
| `backends.<name>.maxTokens` | integer | 8192 | 缺省输出上限（`max_tokens` 未显式传时发出） |
| `defaultBackend` | string | 无 | 缺省使用的后端名 |

校验失败（缺 `backends`、非法 baseURL、未知 capabilities、非法数值、坏 JSON）抛 `ConfigError` → 工具以 `[MISCONFIGURED]` 报错，消息自带修复指引。

**热重载**：每次工具调用重读并解析配置文件；解析失败时沿用上次有效配置（last-good）。原理与坑见 [solutions.md §2.1](solutions.md#21-windows-文件-mtime-不可靠--配置热重载策略)。环境变量通道每次调用重读。

### 1.3 环境变量

| 变量 | 说明 |
| --- | --- |
| `MULTHANDS_CONFIG` | JSON 配置文件绝对路径 |
| `MULTHANDS_BASE_URL` | 单后端快速通道：服务端点（设置后该后端名为 `env`，成为 defaultBackend） |
| `MULTHANDS_MODEL` | 配合上面：模型 id（默认 `local`） |
| `MULTHANDS_API_KEY` | 配合上面：API key（可选） |

## 2. 配置类

### 2.1 `Backend`（`multhands.config`）

| 属性 | 类型 | 说明 |
| --- | --- | --- |
| `name` | str | 后端名 |
| `base_url` | str | 端点（已去尾部 `/`） |
| `model` | str | 模型 id |
| `api_key` | Optional[str] | API key |
| `capabilities` | list[str] | 能力列表（去重保序） |
| `timeout_ms` | int | 单次调用预算 |
| `max_tokens` | int | 缺省输出上限 |
| `has(capability) -> bool` | 方法 | 是否声明某能力 |

### 2.2 `Config`（`multhands.config`）

| 属性/方法 | 说明 |
| --- | --- |
| `backends: dict[str, Backend]` | 后端映射 |
| `default_backend: Optional[str]` | 缺省后端 |
| `source: str` | 配置来源描述（路径 / `environment`） |
| `names: list[str]` | 后端名列表（配置顺序） |
| `get(name, capability) -> Backend` | 按 §2.3 规则解析一个后端 |

### 2.3 后端选择规则

| 优先级 | 规则 | 失败时的行为 |
| --- | --- | --- |
| 1 | 显式 `backend` 名 | 不存在 → `MISCONFIGURED`（列出已知后端） |
| 2 | `defaultBackend` | 不存在/缺能力 → `MISCONFIGURED`（提示显式传名或改配置） |
| 3 | 恰好一个符合能力的后端 | — |
| 4 | 多个符合能力且无 default | `MISCONFIGURED`（提示显式传名或设 `defaultBackend`） |
| 5 | 无候选 | `MISCONFIGURED`（提示配置缺失） |

### 2.4 `ConfigSource`（`multhands.config`）

- `ConfigSource()`：构造时确定配置路径。
- `get() -> Config`：文件通道每次调用重读（last-good 兜底）；环境通道每次调用重读。
- `ConfigError`：所有配置类错误，属性 `message`。

## 3. 工具（Tools）

服务器名：`multhands`；三个工具注册顺序：`local_run`、`local_vision`、`local_status`。

### 3.1 `local_run` — 本地文本推理

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `prompt` | string | 是 | — | 发给本地模型的指令/文本（user 消息） |
| `system` | string | 否 | — | 可选系统指令 |
| `backend` | string | 否 | 见 §2.3 | 指定后端名 |
| `temperature` | number | 否 | — | 采样温度 0–2 |
| `max_tokens` | integer | 否 | 后端 `maxTokens` | 输出上限 |
| `stop` | string[] | 否 | — | 停止序列 |

成功返回：

```json
{
  "text": "…",
  "reasoning": "…（模型输出思考内容时才有）",
  "model": "服务器报告的模型 id",
  "backend": "实际使用的后端名",
  "usage": { "prompt_tokens": 11, "completion_tokens": 4 },
  "elapsed_ms": 452
}
```

### 3.2 `local_vision` — 识图 / OCR / 图片对比

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `mode` | string | 否 | `analyze` | `analyze` / `ocr` / `compare`；自定义 `prompt` 时被忽略 |
| `prompt` | string | 否 | — | 自定义指令（覆盖模板；两者不要同传） |
| `image_paths` | string[] | 否 | — | 本地图片绝对路径 |
| `image_urls` | string[] | 否 | — | `data:image/...` 或 `http(s)://` URL |
| `backend` | string | 否 | 见 §2.3 | 指定后端名（必须声明 `vision` 能力） |
| `temperature` | number | 否 | — | 采样温度（OCR 建议 ~0.2） |
| `max_tokens` | integer | 否 | 后端 `maxTokens` | 输出上限 |
| `stop` | string[] | 否 | — | 停止序列 |

图片来源 = `image_paths` + `image_urls` 合并；两者皆空 → `[INVALID_REQUEST]`。`compare` 要求 2–4 张（同一请求联合推理）。

支持格式：png / jpg / jpeg / webp / gif / bmp；单张 ≤ 20 MB（`images.MAX_IMAGE_BYTES`）。

成功返回：

```json
{
  "text": "…",
  "reasoning": "…（可选）",
  "model": "…",
  "backend": "…",
  "images": 2,
  "usage": { "prompt_tokens": 11, "completion_tokens": 4 },
  "elapsed_ms": 1234
}
```

### 3.3 `local_status` — 后端列表与健康探测

无参数。返回：

```json
{
  "default_backend": "env",
  "config_source": "environment",
  "backends": [
    {
      "name": "env",
      "baseURL": "http://127.0.0.1:5001",
      "model": "koboldcpp",
      "capabilities": ["text", "vision"],
      "reachable": true,
      "note": "ok"
    }
  ]
}
```

探测语义：`GET {baseURL}/v1/models`，超时 = min(`timeoutMs`, 10s)：

| 探测结果 | reachable | note |
| --- | --- | --- |
| 2xx | true | `ok` |
| 401/403 | true | `reachable but key rejected (AUTH)` |
| 其他状态码 | true | `reachable (HTTP <n>)` |
| 连接失败/超时 | false | `not reachable` |

注意：其他状态码也算「可达」——端口上有服务但不是 OpenAI 兼容端点时 `local_status` 会显示 `reachable (HTTP 404)` 之类线索（[solutions.md §2.2](solutions.md#22-配置的端口上跑着无关服务)）。

## 4. 模块与类

### 4.1 `multhands.client`

| 符号 | 说明 |
| --- | --- |
| `async chat_completion(client, backend, *, prompt, system=None, images=None, temperature=None, max_tokens=None, stop=None) -> ChatCompletion` | 一次非流式 OpenAI 兼容调用；`POST {baseURL}/v1/chat/completions`。发送的请求体仅含标准字段 `model` / `messages` / `temperature` / `max_tokens` / `stop`；`images` 非空时 user 消息为多模态 content 数组 |
| `async probe(client, backend) -> (bool, str)` | 健康探测 `GET /v1/models`；返回 (reachable, note) |
| `ChatCompletion(text, model, prompt_tokens, completion_tokens, reasoning=None)` | 完成结果；usage 缺失时按 ~4 字符/token 估算 |
| `LocalError(message, code, hint=None)` | 调用失败；`str()` 形如 `[CODE] message\nHint: ...` |

### 4.2 `multhands.images`

| 符号 | 说明 |
| --- | --- |
| `async image_to_data_url(source, client, timeout_ms) -> str` | 路径 / `data:` / `http(s)://` → `data:image/...;base64`（http(s) 由本服务器下载转码，本地模型无需联网） |
| `async images_to_data_urls(sources, client, timeout_ms) -> list[str]` | 批量转换 |
| `mime_of(path) -> str` | 按扩展名猜 mime |
| `data_url_to_bytes(url) -> (mime, bytes)` | 解析 data URL（仅 base64） |
| `MAX_IMAGE_BYTES = 20971520` | 单张 20 MB 上限 |
| `SUPPORTED_MIMES` | png/jpeg/webp/gif/bmp |
| `ImageError` | 图片来源错误（→ 工具报 `[INVALID_REQUEST]`） |

### 4.3 `multhands.prompts`

| 符号 | 说明 |
| --- | --- |
| `ANALYZE_PROMPT` | 8 段 `# Image Analysis Report` 模板（含 VERBATIM 逐字规则） |
| `OCR_PROMPT` | 逐字提取模板 |
| `COMPARE_PROMPT` | 5 段 `# Image Comparison Report` 模板 |
| `resolve_vision_prompt(mode, prompt=None) -> str` | 自定义 prompt 优先，否则按 mode 选模板 |
| `VISION_FIDELITY_RULE` | 保真规则（逐字转发、不得编造、保留不确定性），附加在工具描述末尾 |
| `VALID_MODES = ("analyze","ocr","compare")` | 合法 mode 集合 |

### 4.4 `multhands.errors`

| 符号 | 说明 |
| --- | --- |
| `LocalCallError(message, code)` | 工具对外的唯一错误类型；`str()` 形如 `[CODE] message`（已带前缀时不重复加） |

### 4.5 `multhands.server`

| 符号 | 说明 |
| --- | --- |
| `mcp: MCPServer` | 服务器实例（name=`multhands`，version=`__version__`） |
| `config_source: ConfigSource` | 模块级配置源（工具每次调用 `get()`） |
| `get_client() -> httpx.AsyncClient` | 模块级复用 HTTP 客户端（懒创建） |
| `parse_args(argv=None)` | CLI 解析（见 §5） |
| `main()` | 启动服务器 |

## 5. CLI

```
multhands [--transport {stdio,sse,streamable-http}] [--host HOST] [--port PORT]
```

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--transport` | `stdio` | 传输方式。零参数启动 = stdio（MCP 客户端的标准拉起方式） |
| `--host` | `127.0.0.1` | sse / streamable-http 的绑定地址（对外开放需显式 `0.0.0.0`） |
| `--port` | `8000` | sse / streamable-http 的绑定端口 |

端点：Streamable HTTP = `http://<host>:<port>/mcp`；SSE = `http://<host>:<port>/sse`。

## 6. 错误码（协议级 `isError=true`）

工具失败按 MCP 规范返回 `CallToolResult.isError=true`，消息形如 `[CODE] message\nHint: ...`。

| code | 来源 | 含义与提示 |
| --- | --- | --- |
| `MISCONFIGURED` | `ConfigError` | 配置缺失/非法（含后端选择失败）；提示配置方式 |
| `INVALID_REQUEST` | 工具参数校验 / `ImageError` | 非法 mode、无图片、compare 图数越界、图片格式/大小/路径问题 |
| `SERVER_NOT_RUNNING` | 连接失败 | 服务未运行/连不上；提示先启动服务、核对 baseURL 端口 |
| `TIMEOUT` | 超预算 | 本地模型太慢；提示调大 `timeoutMs` 或换更小模型 |
| `AUTH` | HTTP 401/403 | key 缺失/错误；提示配 `apiKey`（Unsloth：Settings → API） |
| `CONTEXT_WINDOW_EXCEEDED` | HTTP 400 + 关键词 | 上下文不够；提示缩短输入/少图/换大上下文模型 |
| `EMPTY_RESPONSE` | 无输出 | 视觉场景常因缺 mmproj；提示检查多模态模型与投影器 |
| `RATE_LIMIT` | HTTP 429 | 限流；稍后重试或降低频率 |
| `TRANSPORT` | 其他 HTTP 异常 | 传输层错误 |
| `SERVER` | HTTP ≥500 | 服务端错误 |
| `HTTP_<n>` | 其他非 2xx | 按状态码 |

## 7. OpenAI 兼容 wire 契约

请求（仅这些字段）：`{model, messages, temperature?, max_tokens?, stop?}`；`messages` 为 `{role: system|user, content: string | [{type:text|image_url, ...}]}`；视觉部分 `{"type":"image_url","image_url":{"url":"data:image/...;base64,..."}}`。有 `apiKey` 时携带 `Authorization: Bearer`。

响应解析：`choices[0].message.content`（也可为 parts 数组，取 text 部分拼接）、`message.reasoning_content` 或 `message.reasoning`、`usage.prompt_tokens` / `usage.completion_tokens`（缺失时估算）、`model`（缺失回退请求值）。