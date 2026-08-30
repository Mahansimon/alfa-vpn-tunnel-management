#!/usr/bin/env bash
# گزارش تشخیصی کامل سیستم و پنل (برای ارسال هنگام پشتیبانی)
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib-common.sh
source "$SCRIPT_DIR/lib-common.sh"

OUT="${1:-/tmp/alfa-diagnose-$(date +%Y%m%d-%H%M%S).txt}"
exec > >(tee "$OUT") 2>&1

section() { printf "\n=== %s ===\n" "$1"; }

printf "Alfa VpnTunnel Managment — گزارش تشخیصی\nزمان: %s\n" "$(date -Is)"

section "سیستم‌عامل"
(cat /etc/os-release 2>/dev/null | grep -E 'PRETTY_NAME|VERSION_ID') || echo "نامشخص"
echo "Kernel: $(uname -r)"
echo "Arch:   $(uname -m)"
echo "Uptime: $(uptime -p 2>/dev/null || true)"
echo "Time synced: $(timedatectl show -p NTPSynchronized --value 2>/dev/null || echo unknown)"

section "CPU / RAM / Disk"
echo "CPU cores: $(nproc)"
grep -m1 'model name' /proc/cpuinfo 2>/dev/null || true
free -h 2>/dev/null || true
df -h / /var 2>/dev/null || true

section "Docker"
if command -v docker >/dev/null 2>&1; then
  docker --version
  docker compose version 2>/dev/null || docker-compose --version 2>/dev/null || echo "compose یافت نشد"
  systemctl is-active docker && echo "docker service: active"
else
  echo "Docker نصب نیست."
fi

section "کانتینرهای پنل"
if [[ -f "$ALFA_DIR/docker-compose.yml" ]]; then
  compose ps || echo "دریافت وضعیت ناموفق بود."
else
  echo "پنل در $ALFA_DIR نصب نشده است."
fi

section "پورت‌های در حال گوش دادن"
(ss -lntp 2>/dev/null | head -40) || netstat -lntp 2>/dev/null | head -40 || echo "ابزار بررسی پورت موجود نیست"

section "فایروال"
(ufw status verbose 2>/dev/null || iptables -S 2>/dev/null | head -30) || echo "نامشخص"

section "تنظیمات پنل (بدون Secret)"
if [[ -f "$ALFA_ENV" ]]; then
  grep -vE 'PASSWORD|SECRET|TOKEN|KEY' "$ALFA_ENV" || true
else
  echo ".env یافت نشد"
fi

section "دیتابیس"
if [[ -f "$ALFA_DIR/docker-compose.yml" ]]; then
  compose exec -T postgres pg_isready -U "$(env_get POSTGRES_USER)" 2>/dev/null || echo "پاسخ نمی‌دهد"
  compose exec -T backend alembic current 2>/dev/null || echo "وضعیت migration نامشخص"
fi

section "سلامت پنل"
HTTP_PORT="$(env_get HTTP_PORT 2>/dev/null || echo 8080)"
curl -fsS "http://127.0.0.1:${HTTP_PORT}/health" 2>/dev/null || curl -fsSk "https://127.0.0.1/health" 2>/dev/null \
  || echo "endpoint سلامت پاسخ نداد"
echo
curl -fsS "http://127.0.0.1:${HTTP_PORT}/version" 2>/dev/null || true

section "شبکه"
ip -brief addr 2>/dev/null | head -10 || true
ping -c1 -W3 1.1.1.1 >/dev/null 2>&1 && echo "ICMP بیرونی: OK" || echo "ICMP بیرونی: ناموفق"
getent hosts github.com >/dev/null 2>&1 && echo "DNS: OK" || echo "DNS: ناموفق"

section "Agent محلی (اگر روی همین سرور نصب است)"
if systemctl list-unit-files 2>/dev/null | grep -q alfa-agent; then
  systemctl is-active alfa-agent || true
  journalctl -u alfa-agent -n 20 --no-pager 2>/dev/null || true
else
  echo "Agent روی این سرور نصب نیست."
fi

section "آخرین لاگ‌های پنل"
if [[ -f "$ALFA_DIR/docker-compose.yml" ]]; then
  compose logs --tail 40 backend 2>/dev/null || true
fi

printf "\n\nگزارش ذخیره شد در: %s\n" "$OUT"
