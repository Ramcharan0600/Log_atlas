FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HF_HOME=/app/data/hf
WORKDIR /app
# CPU-only torch keeps the image ~2 GB smaller than the default CUDA build
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu torch
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN mkdir -p /app/data && useradd -m app && chown -R app /app
USER app
EXPOSE 8000
# Alembic is a no-op on SQLite and creates the schema on PostgreSQL.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
