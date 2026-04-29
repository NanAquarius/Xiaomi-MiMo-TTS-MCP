# Xiaomi MiMo TTS MCP

> 简体中文 · [English](./README.md)

一个把小米 MiMo 的「类 chat/completions」TTS 接口封装成标准 [MCP](https://modelcontextprotocol.io)
工具的服务，让 Cherry Studio、Claude Desktop、Continue 等 MCP 客户端可以直接调用
MiMo 进行语音合成、音色设计与音色克隆，**无需自己写适配器**。同时支持小米 MiMo 的
**按量计费**（`sk-…`）与 **Token Plan**（`tp-…`）两种账号；本地 `pip` 一键安装，
或 `docker compose` 一键部署。

## 功能

- 🎙️ `tts_synthesize` —— 内置音色合成（`mimo-v2.5-tts`、`mimo-v2-tts`）
- 🎨 `tts_voice_design` —— 文字描述生成新音色
- 🧬 `tts_voice_clone` —— 用一段参考音频克隆音色
- 🗂️ `list_voices` —— 列出内置音色、可用模型与当前端点
- 💳 根据 API Key 前缀自动路由到正确的 base URL（按量计费 / Token Plan 的 CN·SGP·AMS 集群）
- 🚚 默认 stdio 传输，亦可切换到 Streamable HTTP / SSE
- 🐳 提供 Dockerfile 与 docker-compose，一行命令起服务

## 端点对照

| 计费模式 | API Key 形式 | Base URL |
|---------|-------------|----------|
| 按量计费 | `sk-…` | `https://api.xiaomimimo.com/v1` |
| Token Plan · 中国 | `tp-…` | `https://token-plan-cn.xiaomimimo.com/v1` |
| Token Plan · 新加坡 | `tp-…` | `https://token-plan-sgp.xiaomimimo.com/v1` |
| Token Plan · 欧洲（阿姆斯特丹） | `tp-…` | `https://token-plan-ams.xiaomimimo.com/v1` |

所有请求都使用 `api-key: <KEY>` 头（**不是** `Authorization: Bearer …`），与
[官方文档](https://platform.xiaomimimo.com/docs/usage-guide/speech-synthesis-v2.5)
一致。两种 Key **不能混用**。

## 快速开始

### 方式 A：本地直接跑（stdio）

```bash
git clone https://github.com/NanAquarius/Xiaomi-MiMo-TTS-MCP.git
cd Xiaomi-MiMo-TTS-MCP
pip install .

export MIMO_API_KEY=sk-...     # 或 Token Plan 的 tp-...
xiaomi-mimo-tts-mcp            # 默认 stdio 传输，等客户端连接即可
```

### 方式 B：Docker（Streamable HTTP）

```bash
cp .env.example .env           # 编辑 MIMO_API_KEY
docker compose up -d --build
# MCP 端点：http://localhost:8000/mcp
```

或者直接用 docker：

```bash
docker build -t xiaomi-mimo-tts-mcp .
docker run --rm -p 8000:8000 \
  -e MIMO_API_KEY=tp-... \
  -e MIMO_PLAN=token-plan \
  -e MIMO_REGION=sgp \
  -v "$PWD/tts_output:/data/tts_output" \
  xiaomi-mimo-tts-mcp
```

## 客户端接入

### Cherry Studio（stdio，桌面端推荐）

`设置 → MCP 服务器 → 添加 → 类型: stdio`

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

Token Plan 用户：

```json
{
  "mcpServers": {
    "xiaomi-mimo-tts": {
      "command": "xiaomi-mimo-tts-mcp",
      "env": {
        "MIMO_API_KEY": "tp-...",
        "MIMO_PLAN": "token-plan",
        "MIMO_REGION": "cn"
      }
    }
  }
}
```

### Cherry Studio / 任意客户端（Docker 模式下走 HTTP）

`类型: streamableHttp` —— URL: `http://localhost:8000/mcp`

### Claude Desktop

macOS 配置：`~/Library/Application Support/Claude/claude_desktop_config.json`
Windows 配置：`%APPDATA%\Claude\claude_desktop_config.json`

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

## 工具参考

| 工具 | 必填参数 | 说明 |
|------|---------|------|
| `tts_synthesize` | `text` | 可选 `voice`（默认 `Chloe`）、`style`、`fmt`（`wav`/`mp3`/`pcm16`）、`model` |
| `tts_voice_design` | `text`、`voice_description` | 默认走 `mimo-v2.5-tts-voicedesign` |
| `tts_voice_clone` | `text`、`reference_audio` | `reference_audio` 可以是本地音频路径，也可以是 `data:audio/...;base64,...` 形式 |
| `list_voices` | —— | 返回内置音色、模型列表、当前 plan / base_url / 输出目录 |

合成类工具返回 `{ "path": "...", "format": "...", ... }`，音频会写入
`MIMO_OUTPUT_DIR`（默认 `./tts_output`；Docker 镜像里默认 `/data/tts_output`，
docker-compose 会把它挂到宿主机的 `./tts_output`）。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|-------|-----|
| `MIMO_API_KEY` | —— | **必填**。`sk-…`（按量）或 `tp-…`（Token Plan） |
| `MIMO_PLAN` | 自动识别 | `pay-as-you-go` 或 `token-plan`，未设置时按 Key 前缀自动判断 |
| `MIMO_REGION` | `cn` | Token Plan 集群：`cn` / `sgp` / `ams` |
| `MIMO_BASE_URL` | 自动推导 | 显式设置会覆盖 `MIMO_PLAN` / `MIMO_REGION` |
| `MIMO_OUTPUT_DIR` | `./tts_output` | 音频输出目录 |
| `MCP_TRANSPORT` | `stdio` | `stdio` / `sse` / `streamable-http` |
| `MCP_HOST` | `0.0.0.0` | HTTP 监听地址 |
| `MCP_PORT` | `8000` | HTTP 监听端口 |

## 许可证

MIT —— 见 [LICENSE](./LICENSE)。

本项目非小米官方项目，"MiMo" 商标归原所有者所有。
