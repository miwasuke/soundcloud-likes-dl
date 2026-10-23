# Lambda（arm64）用。Lambda Web Adapter で FastAPI をそのまま動かす
FROM python:3.13-slim

COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.9.1 /lambda-adapter /opt/extensions/lambda-adapter
COPY --from=ghcr.io/astral-sh/uv:0.11.14 /uv /usr/local/bin/uv

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --compile-bytecode
COPY sc_dl ./sc_dl
RUN uv sync --frozen --no-dev --compile-bytecode

# Lambda はファイルシステムが /tmp 以外読み取り専用
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp \
    PORT=8080 \
    AWS_LWA_PORT=8080

CMD ["sh", "-c", "exec uvicorn sc_dl.web:app --host 0.0.0.0 --port $PORT --no-access-log"]
