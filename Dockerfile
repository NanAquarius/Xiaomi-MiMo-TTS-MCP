FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MCP_TRANSPORT=streamable-http \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000 \
    MIMO_OUTPUT_DIR=/data/tts_output

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install .

RUN mkdir -p /data/tts_output
VOLUME ["/data/tts_output"]
EXPOSE 8000

ENTRYPOINT ["xiaomi-mimo-tts-mcp"]
