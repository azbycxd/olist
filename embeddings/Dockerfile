FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir 'fastembed>=0.7,<1' 'fastapi>=0.115,<1' 'uvicorn>=0.35,<1'
COPY embeddings/server.py /app/server.py
ENV FASTEMBED_CACHE_PATH=/models HF_HUB_DISABLE_XET=1
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8002"]
