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
- 🛡️ 内置可选的 Bearer Token 鉴权（`MCP_AUTH_TOKEN`），公网部署更安全
- 🚚 默认 stdio，亦可切换到 Streamable HTTP / SSE
- 🐳 提供 Dockerfile 与 docker-compose，一行命令起服务

## 端点对照

| 计费模式 | API Key 形式 | Base URL |
|---------|-------------|----------|
| 按量计费 | `sk-…` | `https://api.xiaomimimo.com/v1` |
| Token Plan · 中国 | `tp-…` | `https://token-plan-cn.xiaomimimo.com/v1` |
| Token Plan · 新加坡 | `tp-…` | `https://token-plan-sgp.xiaomimimo.com/v1` |
| Token Plan · 欧洲（阿姆斯特丹） | `tp-…` | `https://token-plan-ams.xiaomimimo.com/v1` |

所有请求使用 `api-key: <KEY>` 头（**不是** `Authorization: Bearer …`），与
[官方文档](https://platform.xiaomimimo.com/docs/usage-guide/speech-synthesis-v2.5)
完全一致。两种 Key **不能混用**。

## 快速开始（服务端）

### 方式 A：本地 stdio（仅同一台机器）

```bash
git clone https://github.com/NanAquarius/Xiaomi-MiMo-TTS-MCP.git
cd Xiaomi-MiMo-TTS-MCP
pip install .

export MIMO_API_KEY=sk-...     # 或 Token Plan 的 tp-...
xiaomi-mimo-tts-mcp            # 默认 stdio，等客户端来连
```

### 方式 B：Docker（Streamable HTTP，可远程访问）

```bash
cp .env.example .env           # 填写 MIMO_API_KEY 和 MCP_AUTH_TOKEN
docker compose up -d --build
# MCP 端点：http://<服务器IP>:8000/mcp
```

## 在远程主机上部署 + 在本地 CherryStudio 使用（最常见的场景）

如果 MCP 跑在 VPS 上、CherryStudio 跑在你自己电脑上，**stdio 是不行的**——它只
能本机进程互通。这种情况必须走 HTTP/SSE 传输。

### 步骤 1：在 VPS 上启动并加上鉴权

```bash
cd ~/Xiaomi-MiMo-TTS-MCP

# 生成一个强随机 token
echo "MCP_AUTH_TOKEN=$(openssl rand -hex 32)" >> .env
echo "MIMO_API_KEY=sk-..."                    >> .env   # 或 tp-...

docker compose up -d --build
```

开放防火墙：

```bash
# Ubuntu / Debian (ufw)
sudo ufw allow 8000/tcp

# 云厂商安全组：放行入站 TCP 8000
```

强烈建议在前面再套一层 Caddy / Nginx 加 HTTPS：

```caddy
# /etc/caddy/Caddyfile
mimo.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

然后把 MCP 服务绑到 `127.0.0.1`（`MCP_HOST=127.0.0.1`），只让 Caddy 能访问，
CherryStudio 端连 `https://mimo.example.com/mcp` 即可。

### 步骤 2：在 CherryStudio 里添加这个远程 MCP

`设置 → MCP 服务器 → 添加 → 类型：streamableHttp`（或 `SSE`）

| 字段 | 填什么 |
|------|--------|
| 名称 | `xiaomi-mimo-tts` |
| URL | `http://<你的VPS-IP>:8000/mcp`（或 HTTPS 域名） |
| 自定义 Header | `Authorization: Bearer <你的MCP_AUTH_TOKEN>` |

> 💡 暂时没有域名 / 不想搞 HTTPS？可以用 SSH 隧道：
> `ssh -N -L 8000:127.0.0.1:8000 user@your-vps`，然后让 CherryStudio 连
> `http://127.0.0.1:8000/mcp` 就行。

### 安全提示

- **务必**设置 `MCP_AUTH_TOKEN`，否则只要别人扫到这个端口，就能消耗你的 MiMo 额度。
- 走公网时尽量加 HTTPS，避免 Bearer Token 明文传输。
- 或者干脆不暴露：服务绑 `127.0.0.1`，配合 SSH 隧道 / Tailscale / WireGuard。

## 开箱即用：自然语言提示词示范

接好 MCP 后，**像聊天一样直接说就行**。除了 `text` 和参考音频是必填，其它参数
都有合理默认值，模型会自动选对工具。

| 你直接发什么 | 模型会调用 | 结果 |
|------------|-----------|------|
| `请朗读：今天天气真好，适合出门散步。` | `tts_synthesize` | 默认音色 `Chloe`、wav，返回音频文件路径 |
| `请用 default_zh 这个音色读："欢迎使用小米 MiMo"` | `tts_synthesize`（`voice="default_zh"`） | 切换为指定音色 |
| `用兴奋、快语速的语气读："我中奖啦！"` | `tts_synthesize`（`style="excited, fast"`） | 控制风格/情绪 |
| `请设计一个慵懒的小女孩声音，读："好困啊……"` | `tts_voice_design` | 用文字描述生成全新音色 |
| `请克隆 /data/sample.mp3 的声音，读："Hello, this is me."` | `tts_voice_clone` | 从参考音频克隆音色 |
| `MiMo TTS 都支持哪些音色？` | `list_voices` | 返回内置音色列表和当前端点 |

返回的音频路径会显示在聊天里，CherryStudio 会做成可点击链接；文件实际写在
**服务端**的 `MIMO_OUTPUT_DIR` 下（Docker 默认 `/data/tts_output`，已经挂到宿主机
的 `./tts_output`）。

### 建议直接复制使用的提示词

**1. 最简：纯朗读（什么参数都不用提）**

```
请用 MiMo TTS 朗读：「明天上午九点准时开会，请提前十分钟到场。」
```

**2. 指定内置音色**

```
调用 xiaomi-mimo-tts 工具，用 default_zh 这个音色，把下面这段合成成 wav：
「夜晚的城市像一片亮着灯的森林。」
```

**3. 指定情绪 / 风格**

```
调用 MiMo TTS，风格设置为「温柔，慢速，像睡前故事」，朗读：
「从前有一只小猫，住在一个长满向日葵的院子里……」
```

**4. 设计一个全新音色（voice design）**

```
请用 tts_voice_design 工具：
- 音色描述：年轻男声，带一点慵懒的播音腔
- 朗读内容：「欢迎收听今晚的深夜电台。」
```

**5. 用一段参考音频克隆音色（voice clone）**

```
请用 tts_voice_clone 工具：
- 参考音频：/data/tts_output/me_sample.mp3
- 朗读内容：「Hello world, this is my cloned voice.」
```

> 注意：克隆的参考音频路径必须是 **MCP 进程** 能读到的（也就是服务器上 / Docker
> 容器里的路径）。把样本放到 `/data/tts_output` 或另外挂一个共享目录即可。

## 客户端配置速查

### CherryStudio · stdio（仅本机）

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

### CherryStudio · streamableHttp（远程 VPS）

```json
{
  "mcpServers": {
    "xiaomi-mimo-tts": {
      "type": "streamableHttp",
      "url": "https://mimo.example.com/mcp",
      "headers": { "Authorization": "Bearer <你的MCP_AUTH_TOKEN>" }
    }
  }
}
```

### Claude Desktop（stdio）

macOS：`~/Library/Application Support/Claude/claude_desktop_config.json`
Windows：`%APPDATA%\Claude\claude_desktop_config.json`

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

## 工具参考

| 工具 | 必填 | 可选（含默认值） | 说明 |
|------|-----|----------------|------|
| `tts_synthesize` | `text` | `voice`=`Chloe`、`style`=∅、`fmt`=`wav`、`model`=`mimo-v2.5-tts` | **默认工具**，绝大多数「请朗读……」会落到这里 |
| `tts_voice_design` | `text`、`voice_description` | `fmt`=`wav`、`model`=`mimo-v2.5-tts-voicedesign` | 用一段文字描述生成全新音色 |
| `tts_voice_clone` | `text`、`reference_audio` | `fmt`=`wav`、`model`=`mimo-v2.5-tts-voiceclone` | `reference_audio` = 本地路径 **或** `data:audio/...;base64,…` |
| `list_voices` | — | — | 返回内置音色、模型列表、当前 plan / base_url / 输出目录 |

合成类工具返回 `{ "path": "...", "format": "...", ... }`，音频写入
`MIMO_OUTPUT_DIR`。

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
| `MCP_AUTH_TOKEN` | 未设 | 设了之后，HTTP 请求必须带 `Authorization: Bearer <token>` |

## 许可证

MIT —— 见 [LICENSE](./LICENSE)。

本项目非小米官方项目，"MiMo" 商标归原所有者所有。
