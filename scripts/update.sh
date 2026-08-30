#!/usr/bin/env bash
# به‌روزرسانی پنل: Backup → Pull → Build → Migrate → Health Check → Rollback در صورت خطا
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../installer/lib-common.sh
source "$SCRIPT_DIR/../installer/lib-common.sh"

require_root
log_init
banner
cd "$ALFA_DIR"

info "۱) ساخت پشتیبان پیش از به‌روزرسانی..."
compose exec -T backend python -m app.cli backup create --kind full || warn "پشتیبان‌گیری ناموفق بود."

PREV_COMMIT="$(git -C "$ALFA_DIR" rev-parse HEAD 2>/dev/null || echo '')"

info "۲) دریافت نسخه جدید..."
if [[ -d "$ALFA_DIR/.git" ]]; then
  run git -C "$ALFA_DIR" fetch --all --tags
  BRANCH="$(env_get GITHUB_BRANCH || echo main)"
  run git -C "$ALFA_DIR" reset --hard "origin/${BRANCH}"
else
  warn "این نصب از گیت نیست. فایل‌های جدید را دستی در $ALFA_DIR قرار دهید و اسکریپت را دوباره اجرا کنید."
fi

info "۳) Build و اجرا..."
run compose build
run compose up -d

info "۴) اجرای Migration..."
if ! compose exec -T backend alembic upgrade head; then
  err "Migration ناموفق بود؛ بازگردانی..."
  [[ -n "$PREV_COMMIT" ]] && git -C "$ALFA_DIR" reset --hard "$PREV_COMMIT" && compose build && compose up -d
  die "به‌روزرسانی برگردانده شد. پشتیبان در $ALFA_DATA/backups موجود است."
fi

info "۵) بررسی سلامت..."
HTTP_PORT="$(env_get HTTP_PORT || echo 8080)"
if wait_for_http "http://127.0.0.1:${HTTP_PORT}/health" 30 || wait_for_http "https://127.0.0.1/health" 10; then
  ok "به‌روزرسانی با موفقیت انجام شد."
else
  err "پنل پس از به‌روزرسانی پاسخ نداد؛ بازگردانی..."
  [[ -n "$PREV_COMMIT" ]] && git -C "$ALFA_DIR" reset --hard "$PREV_COMMIT" && compose build && compose up -d
  die "نسخه قبلی بازگردانده شد."
fi
