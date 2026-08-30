# ---------- Backend: FastAPI + Alembic ----------
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# ابزارهای لازم برای pg_dump/pg_restore (پشتیبان‌گیری) و کامپایل چرخ‌ها
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl postgresql-client tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY backend/ /app/
COPY agent/ /app/agent-src/

# اجرای سرویس با کاربر غیرروت
RUN useradd --system --create-home --uid 10001 alfa \
    && mkdir -p /var/lib/alfa/backups /var/log/alfa \
    && chown -R alfa:alfa /app /var/lib/alfa /var/log/alfa

USER alfa

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=5 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
