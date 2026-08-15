# 标准术语表（glossary.md）

术语定义 + 指向权威文档的链接；配置字段/参数细节以 [api.md](api.md) 为准。

## MCP 协议

| 术语 | 定义 |
| --- | --- |
| **MCP**（Model Context Protocol） | 大模型与外部工具/资源间的开放标准协议：JSON-RPC 2.0 消息 + 三种传输 |
| **MCP 服务器 / 客户端** | 本项目 `multhands` 是服务器；opencode、Claude Desktop、Cursor、Cline、Windsurf、Cherry Studio 等是客户端 |
| **工具（tool）** | 服务器暴露给模型的函数式能力；本项目为 `local_run` / `local_vision` / `local_status`（详见 [api.md §3](api.md#3-工具tools)） |
| **CallToolResult** | 工具调用的响应对象：`content`（内容块数组）+ 可选 `structuredContent` + `isError` 标志 |
| **isError** | CallToolResult 的协议级错误标志；为 `true` 时客户端按错误呈现 |
| **结构化内容（structuredContent）** | CallToolResult 可选字段，与 text content 并存 |
| **stdio 传输** | MCP 默认传输：客户端以子进程拉起服务器，stdin/stdout 交换 newline 分隔的 JSON-RPC 消息；零参数启动即此模式 |
| **SSE 传输** | 基于 Server-Sent Events 的旧式网络传输，端点 `/sse` |
| **Streamable HTTP** | 推荐网络传输，端点 `/mcp`：initialize 后服务器签发 **会话 ID（Mcp-Session-Id）**须逐请求回传；客户端 `Accept` 须含 `application/json` 与 `text/event-stream`（坑见 [solutions.md §1.4](solutions.md#14-streamable-http-的三个必踩点)） |
| **协议版本（protocolVersion）** | 握手协商的规范版本；本项目实测 2024-11-05 / 2025-03-26 / 2025-06-18 / 2025-11-25 |
| **健康探测（probe）** | 对后端的 `GET /v1/models` 存活检查；语义见 [api.md §3.3](api.md#33-local_status--后端列表与健康探测) |

## 本地推理

| 术语 | 定义 |
| --- | --- |
| **主模型（在线模型）** | 用户的线上大模型（对话主脑）；始终是决策者 |
| **本地模型** | 运行在本机的开源模型，只经工具触达 |
| **分流（offload）** | 把机械、重复、视觉类劳动从主模型交给本地模型，节省主模型 token |
| **后端（backend）** | 配置中的一个 OpenAI 兼容端点条目；字段见 [api.md §1.2](api.md#12-json-配置文件格式) |
| **capabilities（能力）** | 后端声明的任务类别：`text` / `vision`；按能力挑选后端 |
| **defaultBackend** | 配置的缺省后端；选择规则见 [api.md §2.3](api.md#23-后端选择规则) |
| **KoboldCpp** | LostRuins 的 llama.cpp 图形化服务器；默认端口 5001；`.kcpps` 保存启动配置（含 `mmproj`）；支持 `reasoning_content` |
| **Unsloth Desktop** | Unsloth 桌面应用（Studio API）；默认端口 8888；请求须带 `Authorization: Bearer sk-unsloth-…`（Settings → API 创建） |
| **llama.cpp server（llama-server）** | llama.cpp 官方 OpenAI 兼容服务器；`/props` 可查模型信息 |
| **LM Studio** | 桌面推理软件；默认端口 1234 |
| **Ollama** | 本地模型管理器；OpenAI 兼容 API 在 `/v1`，默认端口 11434 |
| **OpenAI 兼容 API** | 共同实现的 `POST /v1/chat/completions` 约定；本项目 wire 契约见 [api.md §7](api.md#7-openai-兼容-wire-契约) |
| **GGUF** | llama.cpp 生态的模型文件格式 |
| **mmproj（投影器）** | 多模态模型的视觉投影器；缺它则视觉调用看不到图（[solutions.md §2.3](solutions.md#23-视觉调用总失败缺-mmproj)） |
| **多模态模型** | 能同时接收文本与图像的模型 |
| **reasoning_content** | gemma/qwen3 等模型的思考输出；本项目透传为 `reasoning` 字段 |

## 图像与视觉

| 术语 | 定义 |
| --- | --- |
| **data URL** | `data:image/png;base64,...` 内联图片，随请求体直接发给本地模型 |
| **image_paths / image_urls** | 视觉工具的图片来源参数：本地路径 / data 或 http(s) URL |
| **OCR** | 视觉模式：逐字提取图中文字（不改错字、不丢符号） |
| **analyze** | 视觉模式：输出 8 段 `# Image Analysis Report` |
| **compare** | 视觉模式：2–4 张图联合推理，输出 5 段 `# Image Comparison Report` |
| **VERBATIM（逐字）** | 报告模板的强制规则：文字必须逐字转录 |
| **保真规则（fidelity rule）** | 视觉工具描述上的规则：主模型转发本地输出时不得改写、删减或编造 |

## 本项目工程

| 术语 | 定义 |
| --- | --- |
| **纯客户端（pure client）** | 本项目定位：只发 HTTP；不启动/停止进程、不写文件、不改环境变量 |
| **热重载（hot reload）** | 每次工具调用重读配置（[solutions.md §2.1](solutions.md#21-windows-文件-mtime-不可靠--配置热重载策略)） |
| **last-good 兜底** | 配置 JSON 暂时非法时沿用上次有效配置 |
| **错误码（error code）** | 错误消息的稳定前缀 `[CODE]`；完整表见 [api.md §6](api.md#6-错误码协议级-iserrortrue) |
| **Hint** | 错误消息附带的可操作提示，模型可照做自愈 |
| **fakeserver** | 测试用进程内 OpenAI 兼容假服务器（`tests/fakeserver.py`） |
| **官方客户端（official client）** | MCP SDK 自带的 `mcp.client` 实现；e2e 测试用它验证真实线上行为 |
| **uv tool** | uv 的隔离工具安装机制（`uv tool install .`），安装卸载零残留 |

## 外部生态

| 术语 | 定义 |
| --- | --- |
| **DeepSeek Harness** | 设计参照物 `dsh-koboldcpp-hands` / `dsh-unsloth-hands` 所插的 Agent 平台（本项目不依赖它） |
| **opencode / Claude Desktop / Cursor / Cline / Windsurf / Cherry Studio** | 已验证/文档化的 MCP 客户端，接入见 [README「接入各平台」](../README.md) |