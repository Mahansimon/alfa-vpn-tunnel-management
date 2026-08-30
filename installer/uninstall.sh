#!/usr/bin/env bash
# حذف کامل پنل Alfa VpnTunnel Managment
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib-common.sh
source "$SCRIPT_DIR/lib-common.sh"

FORCE=0
KEEP_DATA=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes|-y) FORCE=1; shift ;;
    --keep-data) KEEP_DATA=1; shift ;;
    *) shift ;;
  esac
done

require_root
log_init
banner
warn "این عملیات پنل، کانتینرها و (در صورت تأیید) دیتابیس را حذف می‌کند."
warn "موارد حذف‌شدنی: $ALFA_DIR ، کانتینرها و volumeها، سرویس alfa-panel"

if (( FORCE == 0 )); then
  read -rp "قبل از حذف، یک فایل پشتیبان ساخته شود؟ [Y/n]: " ans_backup || true
  if [[ ! "${ans_backup:-Y}" =~ ^[Nn] ]]; then
    if compose ps >/dev/null 2>&1; then
      info "ساخت پشتیبان..."
      compose exec -T backend python -m app.cli backup create --kind full || warn "ساخت پشتیبان ناموفق بود."
      ok "پشتیبان در $ALFA_DATA/backups ذخیره شد."
    fi
  fi
  read -rp "برای تأیید حذف، عبارت DELETE را تایپ کنید: " confirm || true
  [[ "$confirm" == "DELETE" ]] || die "حذف لغو شد."
fi

info "توقف و حذف کانتینرها..."
if [[ -f "$ALFA_DIR/docker-compose.yml" ]]; then
  if (( KEEP_DATA == 1 )); then compose down --remove-orphans || true
  else compose down --remove-orphans -v || true; fi
fi
systemctl disable --now alfa-panel.service >/dev/null 2>&1 || true
rm -f /etc/systemd/system/alfa-panel.service
systemctl daemon-reload

if (( KEEP_DATA == 0 )); then
  read -rp "پوشه داده ($ALFA_DATA) هم حذف شود؟ [y/N]: " ans_data || true
  if [[ "${ans_data:-N}" =~ ^[Yy] ]]; then rm -rf "$ALFA_DATA"; ok "داده‌ها حذف شدند."
  else ok "داده‌ها در $ALFA_DATA باقی ماندند."; fi
fi
rm -rf "$ALFA_DIR"
ok "پنل حذف شد."
info "برای حذف Agent روی هر سرور:"
info "  systemctl disable --now alfa-agent && rm -rf /opt/alfa-agent /etc/alfa-agent /var/lib/alfa-agent"
