"""Xiaomi MiMo TTS MCP server.

Wraps Xiaomi MiMo's chat-completions-style TTS endpoint as MCP tools that any
MCP-compatible client (Cherry Studio, Claude Desktop, Continue, ...) can call.

Aligned with the official docs:
  - Pay-as-you-go (key prefix `sk-`):
        https://api.xiaomimimo.com/v1
  - Token Plan (key prefix `tp-`), pick one regional cluster:
        https://token-plan-cn.xiaomimimo.com/v1   (China)
        https://token-plan-sgp.xiaomimimo.com/v1  (Singapore)
        https://token-plan-ams.xiaomimimo.com/v1  (Europe / Amsterdam)

Auth header is `api-key: <KEY>` (NOT the OpenAI-style `Authorization: Bearer`).

Exposed tools:
  - tts_synthesize     : built-in voice synthesis (default tool, use first)
  - tts_voice_design   : generate audio with a voice described in text
  - tts_voice_clone    : clone a voice from a reference audio file
  - list_voices        : show built-in voices / supported models / current endpoint
"""

from __future__ import annotations

import argparse
import base64
import mimetypes
import os
import re
import sys
import time
from pathlib import Path
from typing import Annotated, Any, Literal, Optional

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.utilities.types import Audio
from pydantic import Field

# ---------------------------------------------------------------------------
# Endpoint resolution
# ---------------------------------------------------------------------------

PAY_AS_YOU_GO_BASE_URL = "https://api.xiaomimimo.com/v1"
TOKEN_PLAN_BASE_URLS: dict[str, str] = {
    "cn":  "https://token-plan-cn.xiaomimimo.com/v1",
    "sgp": "https://token-plan-sgp.xiaomimimo.com/v1",
    "ams": "https://token-plan-ams.xiaomimimo.com/v1",
}

DEFAULT_MODEL = "mimo-v2.5-tts"
DEFAULT_VOICE = "Chloe"
DEFAULT_FORMAT: Literal["wav", "mp3", "pcm16"] = "wav"
DEFAULT_TIMEOUT = 120.0

BUILT_IN_VOICES: list[str] = [
    "Chloe",
    "mimo_default",
    "default_en",
    "default_zh",
]


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def _resolve_base_url(api_key: str | None) -> tuple[str, str]:
    """Return (base_url, plan) where plan ∈ {'pay-as-you-go','token-plan','custom'}.

    Resolution order:
      1. MIMO_BASE_URL env var (explicit override) → 'custom'.
      2. MIMO_PLAN=token-plan + MIMO_REGION (cn|sgp|ams) → token-plan cluster.
      3. MIMO_PLAN=pay-as-you-go → pay-as-you-go endpoint.
      4. Auto-detect from key prefix: 'tp-' → token-plan, 'sk-' → pay-as-you-go.
      5. Fallback to pay-as-you-go.
    """
    explicit = _env("MIMO_BASE_URL")
    if explicit:
        return explicit.rstrip("/"), "custom"

    plan = (_env("MIMO_PLAN") or "").strip().lower().replace("_", "-")
    region = (_env("MIMO_REGION") or "cn").strip().lower()

    if plan == "token-plan":
        url = TOKEN_PLAN_BASE_URLS.get(region)
        if not url:
            raise RuntimeError(
                f"Unknown MIMO_REGION={region!r}; expected one of "
                f"{sorted(TOKEN_PLAN_BASE_URLS)}"
            )
        return url, "token-plan"
    if plan in ("pay-as-you-go", "payg", "paygo"):
        return PAY_AS_YOU_GO_BASE_URL, "pay-as-you-go"

    if api_key:
        if api_key.startswith("tp-"):
            return TOKEN_PLAN_BASE_URLS.get(region, TOKEN_PLAN_BASE_URLS["cn"]), "token-plan"
        if api_key.startswith("sk-"):
            return PAY_AS_YOU_GO_BASE_URL, "pay-as-you-go"

    return PAY_AS_YOU_GO_BASE_URL, "pay-as-you-go"


API_KEY = _env("MIMO_API_KEY")
BASE_URL, PLAN = _resolve_base_url(API_KEY)
OUTPUT_DIR = Path(_env("MIMO_OUTPUT_DIR", "./tts_output") or "./tts_output").resolve()
AUTH_TOKEN = _env("MCP_AUTH_TOKEN")  # optional bearer auth for HTTP transport


def _split_csv(name: str) -> list[str]:
    raw = _env(name, "") or ""
    return [x.strip() for x in raw.split(",") if x.strip()]


ALLOWED_HOSTS = _split_csv("MCP_ALLOWED_HOSTS")
ALLOWED_ORIGINS = _split_csv("MCP_ALLOWED_ORIGINS")
DISABLE_DNS_REBINDING = (_env("MCP_DISABLE_DNS_REBINDING_PROTECTION", "") or "").lower() in (
    "1", "true", "yes", "on",
)

# Sanity warning on key/plan mismatch.
if API_KEY:
    if PLAN == "token-plan" and API_KEY.startswith("sk-"):
        print(
            "[xiaomi-mimo-tts-mcp] WARNING: Using a Token Plan base URL with an "
            "'sk-' key. Token Plan only accepts 'tp-' keys.",
            file=sys.stderr,
        )
    elif PLAN == "pay-as-you-go" and API_KEY.startswith("tp-"):
        print(
            "[xiaomi-mimo-tts-mcp] WARNING: Using the pay-as-you-go base URL with "
            "a 'tp-' key. Set MIMO_PLAN=token-plan and MIMO_REGION accordingly.",
            file=sys.stderr,
        )

mcp = FastMCP("xiaomi-mimo-tts")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAFE = re.compile(r"[^A-Za-z0-9_\-]+")


def _safe_stem(text: str, max_len: int = 32) -> str:
    stem = _SAFE.sub("_", text.strip())[:max_len].strip("_")
    return stem or "audio"


def _save_audio(b64_data: str, fmt: str, hint: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    path = OUTPUT_DIR / f"mimo_{ts}_{_safe_stem(hint)}.{fmt}"
    path.write_bytes(base64.b64decode(b64_data))
    return path


def _check_api_key() -> str:
    if not API_KEY:
        raise RuntimeError(
            "MIMO_API_KEY is not set. Get one from "
            "https://platform.xiaomimimo.com (sk-... for pay-as-you-go, "
            "tp-... for Token Plan) and export it before starting the MCP server."
        )
    return API_KEY


def _post_chat(payload: dict[str, Any]) -> dict[str, Any]:
    headers = {
        "api-key": _check_api_key(),
        "Content-Type": "application/json",
    }
    url = f"{BASE_URL}/chat/completions"
    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        r = client.post(url, headers=headers, json=payload)
        if r.status_code >= 400:
            raise RuntimeError(
                f"MiMo TTS API error {r.status_code} from {url}: {r.text[:500]}"
            )
        return r.json()


def _extract_audio(resp: dict[str, Any]) -> tuple[str, str]:
    """Return (base64_data, format)."""
    try:
        msg = resp["choices"][0]["message"]
        audio = msg["audio"]
        return audio["data"], audio.get("format", DEFAULT_FORMAT)
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected response shape: {resp}") from exc


def _read_voice_reference(ref: str) -> str:
    """Convert a path or already-formatted data URI into a data URI string."""
    if ref.startswith("data:"):
        return ref
    p = Path(ref).expanduser()
    if not p.is_file():
        raise FileNotFoundError(f"Reference audio not found: {ref}")
    mime = mimetypes.guess_type(p.name)[0] or "audio/mpeg"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool(structured_output=False)
def tts_synthesize(
    text: Annotated[
        str,
        Field(description="要朗读 / 合成的文本内容（assistant content）。Text to be read aloud."),
    ],
    voice: Annotated[
        str,
        Field(description="内置音色名（Built-in voice），默认 'Chloe'。可选：Chloe / mimo_default / default_en / default_zh。"),
    ] = DEFAULT_VOICE,
    style: Annotated[
        Optional[str],
        Field(description="可选的风格 / 情绪描述（user content），例如 'cheerful, fast' 或 '温柔，慢速'。"),
    ] = None,
    fmt: Annotated[
        Literal["wav", "mp3", "pcm16"],
        Field(description="输出音频格式，默认 wav。"),
    ] = DEFAULT_FORMAT,
    model: Annotated[
        str,
        Field(description="MiMo TTS 模型 ID，默认 'mimo-v2.5-tts'。"),
    ] = DEFAULT_MODEL,
) -> list[Any]:
    """**默认 TTS 工具**：用 MiMo 内置音色把一段文本合成语音并直接返回可播放的音频。

    适用场景（Use this when）：
    - 用户说「请朗读 XXX」「读一下这段：XXX」「Read this aloud: ...」
    - 用户没有明确给出参考音频，也没有要求生成全新音色
    - 用户给了风格描述（"用兴奋的语气"、"慢一点"、"cheerful, fast"）→ 放到 `style`

    只有 `text` 是必填，其他全部有合理默认值。返回值是 [AudioContent, 元数据 JSON]，
    支持音频内容的 MCP 客户端会直接播放出声音，不需要再下载文件。
    """
    messages: list[dict[str, str]] = []
    if style:
        messages.append({"role": "user", "content": style})
    messages.append({"role": "assistant", "content": text})

    payload = {
        "model": model,
        "messages": messages,
        "audio": {"format": fmt, "voice": voice},
    }
    resp = _post_chat(payload)
    b64, real_fmt = _extract_audio(resp)
    path = _save_audio(b64, real_fmt, text[:24])
    return [
        Audio(path=str(path)),
        {"path": str(path), "format": real_fmt, "voice": voice, "model": model},
    ]


@mcp.tool(structured_output=False)
def tts_voice_design(
    text: Annotated[str, Field(description="要朗读的文本内容（assistant content）。")],
    voice_description: Annotated[
        str,
        Field(description="对目标音色的自然语言描述，例如 '年轻男声，温暖低沉' / 'a warm young female voice'。"),
    ],
    fmt: Annotated[
        Literal["wav", "mp3", "pcm16"],
        Field(description="输出音频格式，默认 wav。"),
    ] = DEFAULT_FORMAT,
    model: Annotated[
        str,
        Field(description="必须使用支持 voice design 的模型。"),
    ] = "mimo-v2.5-tts-voicedesign",
) -> list[Any]:
    """**音色设计**：根据「文字描述」生成一种全新音色，再用它朗读文本。

    适用场景：
    - 用户描述了一种**还没有**的音色，例如「用一个慵懒的小女孩声音读……」
    - 用户说「自定义一个声音 / 设计一个声音 / design a voice」
    - 内置音色 (Chloe / default_en …) 不能满足时

    需要 `text` 和 `voice_description` 两个参数。返回 [AudioContent, 元数据 JSON]，
    支持音频内容的 MCP 客户端会直接播放出声音。
    """
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": voice_description},
            {"role": "assistant", "content": text},
        ],
        "audio": {"format": fmt},
    }
    resp = _post_chat(payload)
    b64, real_fmt = _extract_audio(resp)
    path = _save_audio(b64, real_fmt, text[:24])
    return [
        Audio(path=str(path)),
        {"path": str(path), "format": real_fmt, "model": model},
    ]


@mcp.tool(structured_output=False)
def tts_voice_clone(
    text: Annotated[str, Field(description="要朗读的文本内容（assistant content）。")],
    reference_audio: Annotated[
        str,
        Field(description="参考音频：本地音频文件路径，或 'data:audio/...;base64,...' 形式的 data URI。"),
    ],
    fmt: Annotated[
        Literal["wav", "mp3", "pcm16"],
        Field(description="输出音频格式，默认 wav。"),
    ] = DEFAULT_FORMAT,
    model: Annotated[
        str,
        Field(description="必须使用支持 voice clone 的模型。"),
    ] = "mimo-v2.5-tts-voiceclone",
) -> list[Any]:
    """**音色克隆**：从一段参考音频里克隆出说话人音色，并用它朗读文本。

    适用场景：
    - 用户说「请克隆 /path/xx.mp3 的声音读……」「Clone the voice in this file: ...」
    - 用户提供了一段音频样本，要求"用 ta 的声音"

    需要 `text` 和 `reference_audio`。`reference_audio` 可以是本地路径或 base64 data URI。
    返回 [AudioContent, 元数据 JSON]，支持音频内容的 MCP 客户端会直接播放出声音。
    """
    voice_uri = _read_voice_reference(reference_audio)
    payload = {
        "model": model,
        "messages": [{"role": "assistant", "content": text}],
        "audio": {"format": fmt, "voice": voice_uri},
    }
    resp = _post_chat(payload)
    b64, real_fmt = _extract_audio(resp)
    path = _save_audio(b64, real_fmt, text[:24])
    return [
        Audio(path=str(path)),
        {"path": str(path), "format": real_fmt, "model": model},
    ]


@mcp.tool()
def list_voices() -> dict[str, Any]:
    """List known built-in voices, supported TTS model ids, and the active endpoint.

    适用场景：用户想知道「都有哪些音色 / 当前接的是哪个端点」时调用。
    """
    return {
        "built_in_voices": BUILT_IN_VOICES,
        "models": [
            "mimo-v2.5-tts",
            "mimo-v2.5-tts-voicedesign",
            "mimo-v2.5-tts-voiceclone",
            "mimo-v2-tts",
        ],
        "plan": PLAN,
        "base_url": BASE_URL,
        "output_dir": str(OUTPUT_DIR),
    }


# ---------------------------------------------------------------------------
# Optional bearer auth middleware (HTTP transports only)
# ---------------------------------------------------------------------------

class _BearerAuthASGI:
    """Minimal ASGI middleware that requires `Authorization: Bearer <token>`."""

    def __init__(self, app: Any, token: str) -> None:
        self.app = app
        self.expected = f"Bearer {token}".encode()

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        if headers.get(b"authorization", b"") != self.expected:
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"www-authenticate", b'Bearer realm="mimo-tts-mcp"'),
                ],
            })
            await send({
                "type": "http.response.body",
                "body": b'{"error":"unauthorized"}',
            })
            return
        await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(prog="xiaomi-mimo-tts-mcp")
    parser.add_argument(
        "--transport",
        default=os.environ.get("MCP_TRANSPORT", "stdio"),
        choices=["stdio", "sse", "streamable-http"],
        help="MCP transport (default: stdio).",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("MCP_HOST", "0.0.0.0"),
        help="Host to bind for sse/streamable-http transports.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MCP_PORT", "8000")),
        help="Port to bind for sse/streamable-http transports.",
    )
    args = parser.parse_args()

    print(
        f"[xiaomi-mimo-tts-mcp] transport={args.transport} plan={PLAN} "
        f"base_url={BASE_URL} output_dir={OUTPUT_DIR} "
        f"auth={'on' if AUTH_TOKEN else 'off'}",
        file=sys.stderr,
    )

    if args.transport == "stdio":
        mcp.run(transport="stdio")
        return

    # HTTP transports — configure DNS-rebinding protection, wrap with optional
    # bearer auth, then run via uvicorn.
    import uvicorn  # imported lazily so stdio mode has no extra cost
    from mcp.server.transport_security import TransportSecuritySettings

    sec = mcp.settings.transport_security or TransportSecuritySettings()
    bound_to_loopback = args.host in ("127.0.0.1", "localhost", "::1")

    if DISABLE_DNS_REBINDING:
        sec.enable_dns_rebinding_protection = False
    elif ALLOWED_HOSTS or ALLOWED_ORIGINS:
        sec.enable_dns_rebinding_protection = True
        if ALLOWED_HOSTS:
            sec.allowed_hosts = ALLOWED_HOSTS
        if ALLOWED_ORIGINS:
            sec.allowed_origins = ALLOWED_ORIGINS
    elif AUTH_TOKEN and not bound_to_loopback:
        # Bearer auth already prevents the attack class DNS-rebinding mitigates;
        # auto-relax so the server is reachable from the configured public host.
        sec.enable_dns_rebinding_protection = False
        print(
            "[xiaomi-mimo-tts-mcp] DNS rebinding protection auto-disabled "
            "because MCP_AUTH_TOKEN is set. Set MCP_ALLOWED_HOSTS / "
            "MCP_ALLOWED_ORIGINS to restrict explicitly.",
            file=sys.stderr,
        )
    mcp.settings.transport_security = sec

    if args.transport == "streamable-http":
        app = mcp.streamable_http_app()
    else:  # sse
        app = mcp.sse_app()

    if AUTH_TOKEN:
        app = _BearerAuthASGI(app, AUTH_TOKEN)
    elif args.host not in ("127.0.0.1", "localhost"):
        print(
            "[xiaomi-mimo-tts-mcp] WARNING: HTTP transport bound to "
            f"{args.host} without MCP_AUTH_TOKEN. Anyone who can reach this "
            "port can use your MiMo API quota. Set MCP_AUTH_TOKEN or bind to "
            "127.0.0.1 + tunnel.",
            file=sys.stderr,
        )

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
