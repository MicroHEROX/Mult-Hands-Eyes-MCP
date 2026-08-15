# mult-hands-eyes-mcp

npm wrapper for [Mult Hands Eyes MCP](https://github.com/MicroHEROX/Mult-Hands-Eyes-MCP) — the MCP server that gives online LLMs local hands (text) and eyes (vision) via OpenAI-compatible local inference services.

```sh
npx mult-hands-eyes-mcp            # MCP server over stdio
npx mult-hands-eyes-mcp --transport streamable-http --host 0.0.0.0 --port 8020
```

- Bundles the same Python server; requires **Python ≥ 3.10** on PATH.
- First run creates a private venv in your OS temp dir and installs two small runtime deps (`mcp`, `httpx`) into it — nothing else touches your system.
- Configuration is the same as the main project (env `MULTHANDS_CONFIG` → `multhands.json`, or `MULTHANDS_BASE_URL`). See the [main README](https://github.com/MicroHEROX/Mult-Hands-Eyes-MCP) for full docs.

## License

MIT — see [LICENSE](LICENSE).