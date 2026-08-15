# Mult Hands Eyes MCP v0.1.0

First public release.

## Highlights

- **`local_run`** — offload repetitive text work (rewrites, translations, string munging, deduplication, summaries, structured extraction) to any OpenAI-compatible local inference service.
- **`local_vision`** — OCR, image analysis, and 2–4-image comparison on a local multimodal model, with structured report templates (`analyze` / `ocr` / `compare`) and a verbatim fidelity rule. Gives text-only online models a way to "see" images.
- **`local_status`** — backend listing with live health probes.
- **Multi-backend config** — one JSON file (`MULTHANDS_CONFIG`), per-backend `text`/`vision` capabilities, hot reload with last-good fallback; plus a quick single-backend env-var mode.
- **Transports** — stdio (default), SSE, Streamable HTTP; protocol versions 2024-11-05 / 2025-03-26 / 2025-06-18 / 2025-11-25 verified against the official MCP client.
- **Spec-compliant errors** — protocol-level `CallToolResult.isError=true` with stable `[CODE]` prefixes and actionable hints.
- **Pure client** — never starts/stops processes, never writes files; installs and uninstalls with zero residue.
- **81 automated tests** across five layers, including official-MCP-client end-to-end tests and real-Unsloth error-path tests.

## Install

```sh
git clone https://github.com/MicroHEROX/Mult-Hands-Eyes-MCP.git
cd Mult-Hands-Eyes-MCP
uv tool install .
```

or via npm: `npx mult-hands-eyes-mcp` (bundled Python server, self-contained venv bootstrap).

## Docs

See [README.md](README.md) and [docs/](docs/) (engineering, API reference, glossary, solutions).

## License

MIT — see [LICENSE](LICENSE).

## Thanks

DeepSeek AI / DeepSeek Harness (via the reference plugins dsh-koboldcpp-hands and dsh-unsloth-hands), KoboldCpp, Unsloth, llama.cpp, the MCP project, and the open models running on your machine.