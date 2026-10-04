FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . && useradd --uid 10001 --create-home manhaj
COPY web ./web
COPY config ./config
COPY schemas ./schemas
COPY scripts ./scripts
RUN mkdir -p /app/data && chown -R manhaj:manhaj /app
USER manhaj
EXPOSE 8000
CMD ["uvicorn", "src.asgi:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers"]
