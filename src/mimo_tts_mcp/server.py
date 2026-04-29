"""Xiaomi MiMo TTS MCP server.

Wraps Xiaomi MiMo's chat-completions-style TTS endpoint
(https://api.xiaomimimo.com/v1/chat/completions) as MCP tools that any
MCP-compatible client (Cherry Studio, Claude Desktop, Continue, ...) can call.

Exposed tools:
  - tts_synthesize     : built-in voice synthesis
  - tts_voice_design   : generate audio with a voice described in text
  - tts_voice_clone    : clone a voice from a reference audio file
  - list_voices        : show built-in voices
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
from pydantic import Field

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "https://api.xiaomimimo.com/v1"
DEFAULT_MODEL = "mimo-v2.5-tts"
DEFAULT_VOICE = "Chloe"
DEFAULT_FORMAT: Literal["wav", "mp3", "pcm16"] = "wav"
DEFAULT_TIMEOUT = 120.0

# A non-exhaustive list; voices may be added/removed by Xiaomi over time.
BUILT_IN_VOICES: list[str] = [
    "Chloe",
    "mimo_default",
    "default_en",
    "default_zh",
]


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


API_KEY = _env("MIMO_API_KEY")
BASE_URL = _env("MIMO_BASE_URL", DEFAULT_BASE_URL) or DEFAULT_BASE_URL
OUTPUT_DIR = Path(_env("MIMO_OUTPUT_DIR", "./tts_output") or "./tts_output").resolve()

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
            "https://platform.xiaomimimo.com and export it before starting "
            "the MCP server."
        )
    return API_KEY


def _post_chat(payload: dict[str, Any]) -> dict[str, Any]:
    headers = {
        "api-key": _check_api_key(),
        "Content-Type": "application/json",
    }
    url = BASE_URL.rstrip("/") + "/chat/completions"
    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        r = client.post(url, headers=headers, json=payload)
        if r.status_code >= 400:
            raise RuntimeError(
                f"MiMo TTS API error {r.status_code}: {r.text[:500]}"
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

@mcp.tool()
def tts_synthesize(
    text: Annotated[str, Field(description="Text to be spoken (assistant content).")],
    voice: Annotated[str, Field(description="Built-in voice name, e.g. 'Chloe'.")] = DEFAULT_VOICE,
    style: Annotated[
        Optional[str],
        Field(description="Optional style/emotion description (user content), e.g. 'cheerful, fast'."),
    ] = None,
    fmt: Annotated[Literal["wav", "mp3", "pcm16"], Field(description="Output audio format.")] = DEFAULT_FORMAT,
    model: Annotated[str, Field(description="MiMo TTS model id.")] = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Synthesize speech with a built-in MiMo voice. Returns the saved file path."""
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
    return {"path": str(path), "format": real_fmt, "voice": voice, "model": model}


@mcp.tool()
def tts_voice_design(
    text: Annotated[str, Field(description="Text to be spoken (assistant content).")],
    voice_description: Annotated[
        str,
        Field(description="Natural-language description of the desired voice, e.g. 'young male, warm tone'."),
    ],
    fmt: Annotated[Literal["wav", "mp3", "pcm16"], Field(description="Output audio format.")] = DEFAULT_FORMAT,
    model: Annotated[str, Field(description="Must be a voice-design capable model.")] = "mimo-v2.5-tts-voicedesign",
) -> dict[str, Any]:
    """Synthesize speech using a voice generated from a free-text description."""
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
    return {"path": str(path), "format": real_fmt, "model": model}


@mcp.tool()
def tts_voice_clone(
    text: Annotated[str, Field(description="Text to be spoken (assistant content).")],
    reference_audio: Annotated[
        str,
        Field(description="Path to a reference audio file, or a 'data:audio/...;base64,...' URI."),
    ],
    fmt: Annotated[Literal["wav", "mp3", "pcm16"], Field(description="Output audio format.")] = DEFAULT_FORMAT,
    model: Annotated[str, Field(description="Must be a voice-clone capable model.")] = "mimo-v2.5-tts-voiceclone",
) -> dict[str, Any]:
    """Clone the voice from a reference audio sample and use it to read text."""
    voice_uri = _read_voice_reference(reference_audio)
    payload = {
        "model": model,
        "messages": [{"role": "assistant", "content": text}],
        "audio": {"format": fmt, "voice": voice_uri},
    }
    resp = _post_chat(payload)
    b64, real_fmt = _extract_audio(resp)
    path = _save_audio(b64, real_fmt, text[:24])
    return {"path": str(path), "format": real_fmt, "model": model}


@mcp.tool()
def list_voices() -> dict[str, Any]:
    """List known built-in voices and supported TTS model ids."""
    return {
        "built_in_voices": BUILT_IN_VOICES,
        "models": [
            "mimo-v2.5-tts",
            "mimo-v2.5-tts-voicedesign",
            "mimo-v2.5-tts-voiceclone",
            "mimo-v2-tts",
        ],
        "output_dir": str(OUTPUT_DIR),
    }


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

    if args.transport in ("sse", "streamable-http"):
        mcp.settings.host = args.host
        mcp.settings.port = args.port

    print(
        f"[xiaomi-mimo-tts-mcp] transport={args.transport} "
        f"base_url={BASE_URL} output_dir={OUTPUT_DIR}",
        file=sys.stderr,
    )
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
