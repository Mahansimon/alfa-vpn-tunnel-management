# Dockerfile ریشه = ایمیج بک‌اند (برای سازگاری با ابزارهایی که فقط ریشه را می‌بینند).
# استقرار کامل با docker-compose.yml انجام می‌شود.
# ساخت دستی:  docker build -t alfa-backend -f Dockerfile .
# ایمیج فرانت‌اند:  docker build -t alfa-frontend -f docker/frontend.Dockerfile .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl postgresql-client tzdata && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt
COPY backend/ /app/
RUN useradd --system --create-home --uid 10001 alfa && chown -R alfa:alfa /app
USER alfa
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=5 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
