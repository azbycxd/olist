FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app
COPY pyproject.toml ./
RUN python -c "import tomllib,subprocess; p=tomllib.load(open('pyproject.toml','rb'))['project']; subprocess.check_call(['pip','install','--no-cache-dir',*p['dependencies'],*p['optional-dependencies']['dev']])"
COPY config.py contracts.py db_pool.py Dockerfile docker-compose.yml .env.example ./
COPY scripts ./scripts
COPY eval ./eval
COPY agent ./agent
COPY mcp_olist ./mcp_olist
COPY api ./api
COPY kb ./kb
COPY sql ./sql
COPY tests ./tests
ENTRYPOINT ["python", "-m", "scripts.entrypoint"]
CMD ["python", "-m", "scripts.load_olist", "--profile"]
