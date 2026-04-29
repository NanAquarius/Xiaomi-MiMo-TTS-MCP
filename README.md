# Xiaomi MiMo TTS MCP

An [MCP](https://modelcontextprotocol.io) server that wraps Xiaomi MiMo's
chat-completions-style TTS API into clean MCP tools, so MCP-compatible clients
(Cherry Studio, Claude Desktop, Continue, etc.) can synthesize, design, and
clone voices without any custom adapter. Run it locally with `pip` or one-shot
with Docker / docker compose.

## Features

- 🎙️ `tts_synthesize` — built-in voice TTS (`mimo-v2.5-tts`, `mimo-v2-tts`)
- 🎨 `tts_voice_design` — generate a voice from a text description
- 🧬 `tts_voice_clone` — clone a voice from a reference audio file
- 🗂️ `list_voices` — discover built-in voices / models
- 🚚 stdio (default) **and** Streamable HTTP / SSE transports
- 🐳 One-command Docker / docker-compose deployment

## Quick start

### Option A — local (stdio)

```bash
git clone https://github.com/NanAquarius/Xiaomi-MiMo-TTS-MCP.git
cd Xiaomi-MiMo-TTS-MCP
pip install .

export MIMO_API_KEY=sk-...     # from https://platform.xiaomimimo.com
xiaomi-mimo-tts-mcp            # stdio transport, ready for MCP clients
```

### Option B — Docker (Streamable HTTP)

```bash
cp .env.example .env           # then edit MIMO_API_KEY
docker compose up -d --build
# MCP endpoint: http://localhost:8000/mcp
```

Or with plain Docker:

```bash
docker build -t xiaomi-mimo-tts-mcp .
docker run --rm -p 8000:8000 \
  -e MIMO_API_KEY=sk-... \
  -v "$PWD/tts_output:/data/tts_output" \
  xiaomi-mimo-tts-mcp
```

## Client configuration

### Cherry Studio (stdio, recommended for desktop)

`Settings → MCP Servers → Add → Type: stdio`

```json
{
  "mcpServers": {
    "xiaomi-mimo-tts": {
      "command": "xiaomi-mimo-tts-mcp",
      "env": { "MIMO_API_KEY": "sk-..." }
    }
  }
}
```

### Cherry Studio / any client (HTTP, when using Docker)

`Type: streamableHttp` — URL: `http://localhost:8000/mcp`

### Claude Desktop

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or
`%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "xiaomi-mimo-tts": {
      "command": "xiaomi-mimo-tts-mcp",
      "env": { "MIMO_API_KEY": "sk-..." }
    }
  }
}
```

## Tool reference

| Tool | Required args | Notes |
|------|---------------|-------|
| `tts_synthesize` | `text` | Optional `voice` (default `Chloe`), `style`, `fmt` (`wav`/`mp3`/`pcm16`), `model` |
| `tts_voice_design` | `text`, `voice_description` | Uses `mimo-v2.5-tts-voicedesign` |
| `tts_voice_clone` | `text`, `reference_audio` | `reference_audio` may be a local path or a `data:audio/...;base64,...` URI |
| `list_voices` | — | Returns built-in voices, model ids, output directory |

All synthesize tools return `{ "path": "...", "format": "...", ... }` — the
audio is written to `MIMO_OUTPUT_DIR` (default `./tts_output`, or
`/data/tts_output` in the Docker image, mounted to `./tts_output` by the
provided compose file).

## Environment variables

| Var | Default | Description |
|-----|---------|-------------|
| `MIMO_API_KEY` | — | **Required.** Xiaomi MiMo API key |
| `MIMO_BASE_URL` | `https://api.xiaomimimo.com/v1` | API base URL |
| `MIMO_OUTPUT_DIR` | `./tts_output` | Where audio files are written |
| `MCP_TRANSPORT` | `stdio` | `stdio` / `sse` / `streamable-http` |
| `MCP_HOST` | `0.0.0.0` | HTTP bind host |
| `MCP_PORT` | `8000` | HTTP bind port |

## License

MIT — see [LICENSE](./LICENSE).

Not an official Xiaomi project. "MiMo" is a trademark of its respective owner.
