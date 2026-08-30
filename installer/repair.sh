#!/usr/bin/env bash
# تعمیر خودکار پنل: سرویس‌ها، Docker، دیتابیس، Migration، پورت‌ها، Proxy
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib-common.sh
source "$SCRIPT_DIR/lib-common.sh"

require_root
log_init
banner
info "شروع تعمیر. لاگ: $ALFA_LOG_FILE"
FIXED=0

info "۱) بررسی Docker..."
if ! systemctl is-active --quiet docker; then
  systemctl restart docker && ok "Docker ری‌استارت شد." && FIXED=$((FIXED+1))
else ok "Docker فعال است."; fi

info "۲) بررسی فایل‌های نصب..."
[[ -f "$ALFA_DIR/docker-compose.yml" ]] || die "فایل docker-compose.yml در $ALFA_DIR نیست. پنل نصب نشده است."
[[ -f "$ALFA_ENV" ]] || die "فایل .env پیدا نشد: $ALFA_ENV"
ok "فایل‌های اصلی موجودند."

info "۳) بررسی کانتینرها..."
compose ps || true
for service in postgres redis backend frontend; do
  if ! compose ps --status running 2>/dev/null | grep -q "$service"; then
    warn "سرویس $service در حال اجرا نیست؛ راه‌اندازی مجدد..."
    compose up -d "$service" && FIXED=$((FIXED+1))
  fi
done

info "۴) بررسی دیتابیس..."
if compose exec -T postgres pg_isready -U "$(env_get POSTGRES_USER)" >/dev/null 2>&1; then
  ok "PostgreSQL پاسخ می‌دهد."
else
  warn "PostgreSQL پاسخ نمی‌دهد؛ ری‌استارت..."
  compose restart postgres
  sleep 8
  compose exec -T postgres pg_isready -U "$(env_get POSTGRES_USER)" >/dev/null 2>&1 \
    && { ok "دیتابیس بازگشت."; FIXED=$((FIXED+1)); } || err "دیتابیس همچنان پاسخ نمی‌دهد."
fi

info "۵) بررسی Migrationها..."
CURRENT="$(compose exec -T backend alembic current 2>/dev/null | tail -1 || true)"
HEAD="$(compose exec -T backend alembic heads 2>/dev/null | tail -1 || true)"
log "current=$CURRENT | head=$HEAD"
if [[ "$CURRENT" != *"$(echo "$HEAD" | awk '{print $1}')"* ]]; then
  warn "دیتابیس عقب‌تر است؛ اجرای migration..."
  compose exec -T backend alembic upgrade head && { ok "Migration انجام شد."; FIXED=$((FIXED+1)); }
else
  ok "دیتابیس به‌روز است."
fi

info "۶) بررسی Redis..."
if compose exec -T redis redis-cli ping 2>/dev/null | grep -qi pong; then ok "Redis سالم است."
else warn "Redis پاسخ نداد؛ ری‌استارت..."; compose restart redis && FIXED=$((FIXED+1)); fi

info "۷) بررسی پورت‌ها..."
HTTP_PORT="$(env_get HTTP_PORT || echo 8080)"
port_in_use "$HTTP_PORT" && ok "پورت $HTTP_PORT در حال سرو است." || warn "چیزی روی پورت $HTTP_PORT گوش نمی‌دهد."

info "۸) بررسی Reverse Proxy..."
if compose exec -T frontend nginx -t >/dev/null 2>&1; then
  ok "پیکربندی Nginx معتبر است."
  compose exec -T frontend nginx -s reload >/dev/null 2>&1 || compose restart frontend
else
  warn "پیکربندی Nginx مشکل دارد؛ ری‌استارت سرویس..."
  compose restart frontend && FIXED=$((FIXED+1))
fi

info "۹) بررسی سلامت پنل..."
if wait_for_http "http://127.0.0.1:${HTTP_PORT}/health" 20 || wait_for_http "https://127.0.0.1/health" 10; then
  ok "پنل پاسخ می‌دهد."
else
  err "پنل پاسخ نمی‌دهد. آخرین لاگ‌های backend:"
  compose logs --tail 60 backend || true
fi

info "۱۰) بررسی Agentهای ثبت‌شده..."
compose exec -T backend python -m app.cli server list || warn "دریافت لیست سرورها ناموفق بود."

printf "\n"
ok "تعمیر به پایان رسید. تعداد موارد اصلاح‌شده: $FIXED"
info "اگر مشکل باقی است اجرا کنید: sudo bash $SCRIPT_DIR/diagnose.sh"
