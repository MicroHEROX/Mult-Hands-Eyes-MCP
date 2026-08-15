# 解决方案（solutions.md）

坑、疑难问题与解决方法，附方法论。每条：现象 → 原因 → 解决 → 相关文档链接。

## 1. MCP SDK / 协议坑

### 1.1 MCP SDK 2.0 的 API 变化

- **现象**：`from mcp.server.fastmcp import FastMCP` 报 `ModuleNotFoundError`；工具参数描述全部丢失。
- **原因**：SDK 2.0 把 `FastMCP` 更名为 `mcp.server.mcpserver.MCPServer`，且不再从 docstring 解析参数描述（本项目依赖已更正为 `mcp>=2.0.0`）。
- **解决**：参数写成 `Annotated[类型, Field(description="...")]`；工具描述用 `@mcp.tool(description=...)` 显式传入。
- **相关**：[engineering.md §3.1](engineering.md#31-注册方式)。

### 1.2 docstring 拼接表达式不生效

- **现象**：`"""...""" + SOME_CONST` 作为函数第一条语句时，工具描述为空。
- **原因**：docstring 只在第一条语句是**纯字符串字面量**时成立；拼接表达式使 `fn.__doc__` 为 `None`。
- **解决**：完整文案放常量，经 `description=` 传入（本项目 `LOCAL_*_DESCRIPTION` 的做法）。
- **相关**：[engineering.md §3.1](engineering.md#31-注册方式)。

### 1.3 错误必须走协议级 isError

- **现象**：工具返回 `{"error": ..., "isError": true}` 的 JSON，客户端不按错误处理、模型易忽略。
- **原因**：JSON 里的 `isError` 是数据字段；规范语义是 `CallToolResult.isError`。
- **解决**：工具失败一律**抛出** `LocalCallError`（`[CODE]` + Hint），SDK 自动转为 `isError=true` 结果；已用官方客户端实测。
- **相关**：[api.md §6](api.md#6-错误码协议级-iserrortrue)、[engineering.md §3.2](engineering.md#32-返回值契约)。

### 1.4 Streamable HTTP 的三个必踩点

- **现象**：原始 HTTP 客户端依次得到 `406` / `421` / `-32600 Missing session ID`。
- **原因**（三条规范要求）：① `Accept` 必须含 `application/json` 与 `text/event-stream`；② DNS 重绑定防护要求 `Host` 头带端口且在允许列表；③ initialize 响应的 `Mcp-Session-Id` 须逐请求回传。
- **解决**：逐条照做；断言固化在 `test_transports.py` / `test_e2e.py`。
- **相关**：[api.md §5](api.md#5-cli)。

### 1.5 官方客户端字段是 snake_case（测试侧）

- **现象**：断言 `init.serverInfo.name` / `result.isError` 报 `AttributeError`。
- **原因**：SDK 2.0 的 pydantic 类型用 `server_info` / `is_error`（线上 JSON 仍是 camelCase）。
- **解决**：Python 侧断言用 snake_case；raw JSON-RPC 断言才用 camelCase。

### 1.6 anyio cancel scope 跨任务边界（测试侧）

- **现象**：pytest-asyncio 下把 `stdio_client(...)` 放进 async fixture，报 `Attempted to exit cancel scope in a different task`。
- **原因**：anyio TaskGroup 必须同一任务内进出；pytest fixture 与测试体在不同任务。
- **解决**：客户端上下文放进测试函数内（如 `test_e2e.py` 的 `mcp_session` 助手）。仅影响测试写法，与服务器无关。

## 2. 配置与运行时坑

### 2.1 Windows 文件 mtime 不可靠 → 配置热重载策略

- **现象**：按 mtime 判断配置变更，同一时钟 tick 内的重写检测不到（NTFS 实际粒度约 10–16 ms）。
- **解决**：放弃 mtime 缓存，**每次工具调用重读解析**配置（几 KB，成本可忽略）；解析失败时 last-good 兜底，编辑中途不断服。
- **相关**：[api.md §1.2](api.md#12-json-配置文件格式)。

### 2.2 配置的端口上跑着无关服务

- **现象**：`local_status` 显示可达，但 `local_run` 报 `INVALID_REQUEST` / `EMPTY_RESPONSE` 或返回 HTML 解析失败。
- **原因**：baseURL 指向了非 OpenAI 兼容的 HTTP 服务（探测只看状态码，404 显示 `reachable (HTTP 404)`）。
- **解决**：核对端口与服务类型（KoboldCpp 5001、Unsloth 8888、llama-server 8080、LM Studio 1234、Ollama 11434）；`local_status.note` 给线索；`curl http://127.0.0.1:<port>/v1/models` 人工核对。
- **相关**：[api.md §3.3](api.md#33-local_status--后端列表与健康探测)。

### 2.3 视觉调用总失败：缺 mmproj

- **现象**：文本调用正常，视觉调用空内容，报 `EMPTY_RESPONSE`。
- **原因**：后端是纯文本模型，或没加载多模态模型的 mmproj 投影器（KoboldCpp 无 mmproj 时请求正常完成但模型看不到图）。
- **解决**：KoboldCpp 在 `.kcpps` 配 `"mmproj"`；llama-server 传 `--mmproj`；Unsloth 切换多模态模型。`EMPTY_RESPONSE` 的 Hint 自带此提示。
- **相关**：[api.md §6](api.md#6-错误码协议级-iserrortrue)。

### 2.4 纯文本主模型如何送图

- **现象**：主模型不支持图片输入，无法把图交给 `local_vision`。
- **解决**：走两个显式渠道——`image_paths`（本地绝对路径；opencode 等粘贴图片会落成临时文件路径，模型可直接引用）或 `image_urls`（`data:` / `http(s)://`）。
- **相关**：[api.md §3.2](api.md#32-local_vision--识图--ocr--图片对比)。

### 2.5 Unsloth 的 401 语义

- **现象**：没配 key 时 `local_status` 显示可达但带 AUTH 注释；`local_run` 报 `[AUTH]`。
- **原因**：Unsloth 要求每个请求携带有效 key；401 恰好证明服务在运行。
- **解决**：探测把 401/403 视为可达（note 标注 key 未通过）；真实调用抛 `AUTH` + 提示到 Settings → API 创建 key 填入 `apiKey`。已对真实 Unsloth 实例实测。
- **相关**：[api.md §3.3](api.md#33-local_status--后端列表与健康探测)。

### 2.6 Windows 控制台 GBK 编码

- **现象**：PowerShell 直接跑测试/脚本，打印 em dash 等字符报 `UnicodeEncodeError: 'gbk' codec can't encode`。
- **解决**：调试用 `uv run python -X utf8`（或先 `sys.stdout.reconfigure(encoding='utf-8')`）；MCP 线路上 SDK 按 UTF-8 处理，不受影响。

## 3. 方法论

### 3.1 错误消息自愈化

每个错误 = 稳定 `[CODE]` + 现象 + 可操作 Hint（「先启动服务」「调大 timeoutMs」「去 Settings → API 创建 key」）。目标：主模型读到错误**无需问人**即可自愈。实现：`LocalError(code, hint)` + `LocalCallError` 前缀去重。

### 3.2 结构化视觉报告 + 保真规则

本地视觉模型输出给主模型消费，必须**可机器验证、不可编造**：固定段落（analyze 8 段 / compare 5 段）、VERBATIM 逐字、Uncertainties 段；工具描述附保真规则约束主模型转发行为。相关：[api.md §4.3](api.md#43-multhandsprompts)。

### 3.3 能力分离（capabilities）

`text` / `vision` 分开声明，按能力选后端：纯文本后端接不到视觉请求，default 后端缺能力时给出明确指引。相关：[api.md §2.3](api.md#23-后端选择规则)。

### 3.4 纯客户端边界

服务器只读配置、只读图片、只发 HTTP——无写入、无进程管理、无环境变量修改。安装/卸载边界见 [README「安装/卸载边界」](../README.md)。天然无副作用、可随时卸载。

### 3.5 测试分层与官方客户端验证

单元 → 集成（真实 HTTP 假后端）→ 工具级（协议形态）→ 传输（版本协商）→ e2e（**官方 MCP 客户端**全流程）。行为验证优先用官方 SDK 客户端，保证「客户端视角」真实；真机测试用 `skipif` 自适应环境。相关：[engineering.md §6](engineering.md#6-测试分层)。

### 3.6 OpenAI wire 严格性

请求体只发标准字段（`test_integration` 有专门断言），防止严格服务端拒绝未知字段；usage 缺失时估算并如实返回。相关：[api.md §7](api.md#7-openai-兼容-wire-契约)。