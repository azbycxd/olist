FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY pyproject.toml config.py ./
COPY scripts ./scripts
RUN pip install --no-cache-dir '.[dev]'
COPY sql ./sql
COPY tests ./tests
CMD ["python", "-m", "scripts.load_olist", "--profile"]
