FROM python:3.12-slim
RUN pip install --no-cache-dir uv==0.11.32

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    FASTEMBED_CACHE_PATH=/app/models PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev
# Bake the embedding model into the image so the server never downloads it at startup.
RUN python -c "from loan_file_assistant.embeddings import FastEmbedder; FastEmbedder()"
COPY samples/pdfs ./samples/pdfs
COPY samples/extracted.jso[n] ./samples/

RUN useradd --create-home app && chown -R app /app
USER app
CMD ["loan-file-assistant"]
