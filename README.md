# Xiaomi MiMo TTS MCP

> [简体中文](./README.zh-CN.md) · English

An [MCP](https://modelcontextprotocol.io) server that wraps Xiaomi MiMo's
chat-completions-style TTS API into clean MCP tools, so MCP-compatible clients
(Cherry Studio, Claude Desktop, Continue, …) can synthesize, design, and clone
voices without any custom adapter. Works with both **pay-as-you-go** (`sk-…`
key) and **Token Plan** (`tp-…` key) accounts. Run it locally with `pip` or one
command via Docker / docker compose.

## Features

- 🎙️ `tts_synthesize` — built-in voice TTS (`mimo-v2.5-tts`, `mimo-v2-tts`)
- 🎨 `tts_voice_design` — generate a voice from a text description
- 🧬 `tts_voice_clone` — clone a voice from a reference audio file
- 🗂️ `list_voices` — discover built-in voices, models, and active endpoint
- 💳 Auto-routes to the right base URL for **pay-as-you-go** or **Token Plan**
  (CN / SGP / AMS clusters) based on the key prefix
- 🛡️ Optional bearer-token auth for safe public exposure (`MCP_AUTH_TOKEN`)
- 🚚 stdio (default) **and** Streamable HTTP / SSE transports
- 🐳 One-command Docker / docker-compose deployment

## Endpoint matrix

| Plan | Key format | Base URL |
|------|------------|----------|
| Pay-as-you-go | `sk-…` | `https://api.xiaomimimo.com/v1` |
| Token Plan — China | `tp-…` | `https://token-plan-cn.xiaomimimo.com/v1` |
| Token Plan — Singapore | `tp-…` | `https://token-plan-sgp.xiaomimimo.com/v1` |
| Token Plan — Europe (Amsterdam) | `tp-…` | `https://token-plan-ams.xiaomimimo.com/v1` |

All requests use `api-key: <KEY>` (not `Authorization: Bearer …`), exactly as
the [official docs](https://platform.xiaomimimo.com/docs/usage-guide/speech-synthesis-v2.5)
specify. The two key types are **not** interchangeable.

## Quick start (server side)

### Option A — local (stdio, single machine only)

```bash
git clone https://github.com/NanAquarius/Xiaomi-MiMo-TTS-MCP.git
cd Xiaomi-MiMo-TTS-MCP
pip install .

export MIMO_API_KEY=sk-...    # or tp-... for Token Plan
xiaomi-mimo-tts-mcp           # stdio transport
```

### Option B — Docker (Streamable HTTP, works for remote VPS too)

```bash
cp .env.example .env          # edit MIMO_API_KEY and MCP_AUTH_TOKEN
docker compose up -d --build
# MCP endpoint: http://<server-ip>:8000/mcp
```

## Connecting from a remote machine (the typical case)

If the MCP server runs on a VPS but Cherry Studio runs on your laptop, you
**must** use one of the HTTP transports — stdio only works in-process on the
same host.

### 1. On the VPS — start the server with auth

```bash
cd ~/Xiaomi-MiMo-TTS-MCP

# generate a strong token once
echo "MCP_AUTH_TOKEN=$(openssl rand -hex 32)" >> .env
echo "MIMO_API_KEY=sk-..."                    >> .env   # or tp-...

docker compose up -d --build
```

Open the firewall:

```bash
# Ubuntu / Debian (ufw)
sudo ufw allow 8000/tcp

# Or any cloud-provider security group: allow inbound TCP 8000
```

For HTTPS in production, put **Caddy** or **Nginx** in front (recommended):

```caddy
# /etc/caddy/Caddyfile
mimo.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

…then bind the MCP server to `127.0.0.1` (`MCP_HOST=127.0.0.1`) so only Caddy
can reach it. Cherry Studio connects to `https://mimo.example.com/mcp`.

### 2. In Cherry Studio — add the remote MCP

`Settings → MCP Servers → Add → Type: streamableHttp` (or `SSE`)

| Field | Value |
|-------|-------|
| Name | `xiaomi-mimo-tts` |
| URL | `http://<your-vps-ip>:8000/mcp` (or your HTTPS domain) |
| Headers | `Authorization: Bearer <MCP_AUTH_TOKEN>` |

> 💡 No domain / no HTTPS yet? You can also tunnel through SSH:
> `ssh -N -L 8000:127.0.0.1:8000 user@your-vps`, then point Cherry Studio at
> `http://127.0.0.1:8000/mcp`.

### Security notes

- **Always** set `MCP_AUTH_TOKEN` if the port is reachable from the public
  internet. Without it, anyone who finds the URL can burn your MiMo quota.
- Prefer HTTPS (Caddy / Nginx) so the bearer token is not sent in plaintext.
- Or, don't expose at all: bind to `127.0.0.1` and use SSH tunnels / Tailscale
  / WireGuard.

## Out-of-the-box prompt recipes (zero-config TTS)

Once the MCP is connected in Cherry Studio, **just chat naturally**. The model
will pick the right tool automatically — every required parameter except the
text/reference has a sensible default.

| What you type | Tool the model picks | What happens |
|---------------|----------------------|--------------|
| `请朗读：今天天气真好，适合出门散步。` | `tts_synthesize` | Default voice `Chloe`, wav, returns file path |
| `请用 default_zh 这个音色读："欢迎使用小米 MiMo"` | `tts_synthesize` (`voice="default_zh"`) | Switches voice |
| `用兴奋、快语速的语气读："我中奖啦！"` | `tts_synthesize` (`style="excited, fast"`) | Style/emotion controlled |
| `请设计一个慵懒的小女孩声音，读："好困啊……"` | `tts_voice_design` | Generates a fresh voice from the description |
| `请克隆 /data/sample.mp3 的声音，读："Hello, this is me."` | `tts_voice_clone` | Voice cloned from the reference file |
| `MiMo TTS 都支持哪些音色？` | `list_voices` | Lists built-in voices and the current endpoint |

The audio file path is returned in the chat. Cherry Studio will show it as a
clickable link; the file lives under `MIMO_OUTPUT_DIR` on the **server**
(default `/data/tts_output` inside the container, mounted to `./tts_output`).

### Recommended copy-paste prompts

**1. Plain reading (smallest possible request)**

```
请用 MiMo TTS 朗读：「明天上午九点准时开会，请提前十分钟到场。」
```

**2. With a specific voice**

```
调用 xiaomi-mimo-tts，用 default_zh 这个音色，把下面这段读成一个 wav 文件：
「夜晚的城市像一片亮着灯的森林。」
```

**3. With emotion / style**

```
调用 MiMo TTS 工具，风格设置为「温柔，慢速，像睡前故事」，朗读：
「从前有一只小猫，住在一个长满向日葵的院子里……」
```

**4. Design a brand-new voice**

```
请用 tts_voice_design 工具：
- 音色描述：年轻男声，带一点慵懒的播音腔
- 朗读内容：「欢迎收听今晚的深夜电台。」
```

**5. Clone a voice from a reference file**

```
请用 tts_voice_clone 工具：
- 参考音频：/data/tts_output/me_sample.mp3
- 朗读内容：「Hello world, this is my cloned voice.」
```

> Note: for cloning, the path must be readable **by the MCP process** (i.e. on
> the server / inside the Docker container). Mount your samples into
> `/data/tts_output` or another shared volume.

## Client configuration cheatsheet

### Cherry Studio · stdio (local server only)

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

### Cherry Studio · streamable HTTP (remote VPS)

```json
{
  "mcpServers": {
    "xiaomi-mimo-tts": {
      "type": "streamableHttp",
      "url": "https://mimo.example.com/mcp",
      "headers": { "Authorization": "Bearer <MCP_AUTH_TOKEN>" }
    }
  }
}
```

### Claude Desktop (stdio)

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or
`%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "xiaomi-mimo-tts": {
      "command": "xiaomi-mimo-tts-mcp",
      "env": { "MIMO_API_KEY": "tp-...", "MIMO_PLAN": "token-plan", "MIMO_REGION": "cn" }
    }
  }
}
```

## Tool reference

| Tool | Required | Optional (with defaults) | Notes |
|------|----------|--------------------------|-------|
| `tts_synthesize` | `text` | `voice`=`Chloe`, `style`=∅, `fmt`=`wav`, `model`=`mimo-v2.5-tts` | The default — most "请朗读…" requests land here |
| `tts_voice_design` | `text`, `voice_description` | `fmt`=`wav`, `model`=`mimo-v2.5-tts-voicedesign` | Generates a new voice from a textual description |
| `tts_voice_clone` | `text`, `reference_audio` | `fmt`=`wav`, `model`=`mimo-v2.5-tts-voiceclone` | `reference_audio` = local path **or** `data:audio/...;base64,…` |
| `list_voices` | — | — | Returns voices, models, plan, base_url, output_dir |

Each synthesize tool returns **two MCP content blocks**:

1. **`AudioContent`** — the audio as inline base64 (MIME `audio/wav` etc.),
   so MCP clients with audio support (Claude Desktop, Kelivo, …) **play it
   inline without needing access to the server's filesystem**.
2. **`TextContent`** — JSON metadata `{path, format, voice, model}` for chat
   logs and follow-up tool calls. The same audio is also persisted to
   `MIMO_OUTPUT_DIR` (default `./tts_output`, or `/data/tts_output` in the
   Docker image, mounted to `./tts_output` by the provided compose file).

## Environment variables

| Var | Default | Description |
|-----|---------|-------------|
| `MIMO_API_KEY` | — | **Required.** `sk-…` (pay-as-you-go) or `tp-…` (Token Plan). |
| `MIMO_PLAN` | auto-detect | `pay-as-you-go` or `token-plan`. Auto-detected from the key prefix. |
| `MIMO_REGION` | `cn` | Token Plan cluster: `cn`, `sgp`, or `ams`. |
| `MIMO_BASE_URL` | derived | Hard override that wins over `MIMO_PLAN` / `MIMO_REGION`. |
| `MIMO_OUTPUT_DIR` | `./tts_output` | Where audio files are written. |
| `MCP_TRANSPORT` | `stdio` | `stdio` / `sse` / `streamable-http`. |
| `MCP_HOST` | `0.0.0.0` | HTTP bind host. |
| `MCP_PORT` | `8000` | HTTP bind port. |
| `MCP_AUTH_TOKEN` | unset | If set, HTTP transports require `Authorization: Bearer <token>`. |

## License

MIT — see [LICENSE](./LICENSE).

Not an official Xiaomi project. "MiMo" is a trademark of its respective owner.
