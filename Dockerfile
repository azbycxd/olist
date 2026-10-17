FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY pyproject.toml config.py contracts.py ./
COPY scripts ./scripts
COPY eval ./eval
RUN pip install --no-cache-dir '.[dev]'
COPY sql ./sql
COPY tests ./tests
ENTRYPOINT ["python", "-m", "scripts.entrypoint"]
CMD ["python", "-m", "scripts.load_olist", "--profile"]
