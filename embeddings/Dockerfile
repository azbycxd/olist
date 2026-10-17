FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir 'fastembed==0.9.0' 'fastapi>=0.115,<1' 'uvicorn>=0.35,<1'
COPY embeddings/server.py /app/server.py
COPY mcp_olist/embedding_config.py /app/embedding_config.py
ENV FASTEMBED_CACHE_PATH=/models HF_HOME=/models/hf HF_HUB_DISABLE_XET=1 HF_ENDPOINT=https://hf-mirror.com
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8002"]
