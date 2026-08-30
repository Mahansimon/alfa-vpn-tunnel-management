#!/usr/bin/env bash
# نصب Agent روی سرور لینوکسی (idempotent — اجرای مکرر خرابی ایجاد نمی‌کند)
# اجرا:
#   sudo bash install-agent.sh --panel-url https://panel.example.com --token <ENROLLMENT_TOKEN>
set -Eeuo pipefail

AGENT_USER="alfa-agent"
AGENT_HOME="/opt/alfa-agent"
AGENT_CONF_DIR="/etc/alfa-agent"
AGENT_STATE_DIR="/var/lib/alfa-agent"
AGENT_LOG_DIR="/var/log/alfa-agent"
TUNNEL_DIR="/etc/alfa/tunnels"
BINARY_DIR="/opt/alfa/tunnel-binaries"
AGENT_PORT="9443"
PANEL_URL=""
TOKEN=""
UPGRADE=0
NO_FIREWALL=0
TOTAL=11

C_RESET='\033[0m'; C_RED='\033[1;31m'; C_GREEN='\033[1;32m'; C_YELLOW='\033[1;33m'; C_BOLD='\033[1m'
log()  { printf "%b\n" "$*" >&2; }
ok()   { log "${C_GREEN}✔${C_RESET} $*"; }
warn() { log "${C_YELLOW}!${C_RESET} $*"; }
err()  { log "${C_RED}✘${C_RESET} $*"; }
step() { log "\n${C_BOLD}[$1/$TOTAL]${C_RESET} $2"; }
die()  { err "$*"; exit 1; }

usage() {
  cat <<'USAGE'
استفاده: sudo bash install-agent.sh --panel-url <URL> --token <TOKEN> [گزینه‌ها]
  --panel-url <URL>   آدرس پنل (مثلاً https://panel.example.com)
  --token <TOKEN>      توکن نصب که پنل هنگام افزودن سرور نمایش می‌دهد
  --port <PORT>        پورت Agent (پیش‌فرض 9443)
  --upgrade            فقط به‌روزرسانی فایل‌های Agent
  --no-firewall        تنظیم نکردن فایروال
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --panel-url) PANEL_URL="${2:-}"; shift 2 ;;
    --token) TOKEN="${2:-}"; shift 2 ;;
    --port) AGENT_PORT="${2:-9443}"; shift 2 ;;
    --upgrade) UPGRADE=1; shift ;;
    --no-firewall) NO_FIREWALL=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) warn "گزینه ناشناخته: $1"; shift ;;
  esac
done

[[ "${EUID:-$(id -u)}" -eq 0 ]] || die "این اسکریپت باید با root اجرا شود: sudo bash install-agent.sh ..."

step 1 "بررسی سیستم و معماری..."
[[ -r /etc/os-release ]] || die "سیستم‌عامل قابل تشخیص نیست."
# shellcheck disable=SC1091
. /etc/os-release
case "$(uname -m)" in
  x86_64|amd64) ARCH=amd64 ;;
  aarch64|arm64) ARCH=arm64 ;;
  *) die "معماری $(uname -m) پشتیبانی نمی‌شود (فقط amd64 و arm64)." ;;
esac
[[ -d /run/systemd/system ]] || die "systemd روی این سرور فعال نیست؛ Agent به systemd نیاز دارد."
ok "$PRETTY_NAME / $ARCH"

step 2 "نصب پیش‌نیازها..."
export DEBIAN_FRONTEND=noninteractive
if command -v apt-get >/dev/null 2>&1; then
  apt-get update -y >/dev/null 2>&1 || warn "apt update با هشدار تمام شد."
  apt-get install -y python3 python3-venv ca-certificates curl openssl git sudo iproute2 iputils-ping \
    >/dev/null 2>&1 || warn "برخی بسته‌ها نصب نشدند؛ ادامه می‌دهیم."
elif command -v dnf >/dev/null 2>&1; then
  dnf install -y python3 ca-certificates curl openssl git sudo iproute iputils >/dev/null 2>&1 || true
else
  warn "مدیر بسته شناخته نشد؛ مطمئن شوید python3 و git نصب هستند."
fi
command -v python3 >/dev/null 2>&1 || die "python3 نصب نیست."
PY_OK=$(python3 -c 'import sys; print(1 if sys.version_info >= (3,9) else 0)')
[[ "$PY_OK" == "1" ]] || die "Python 3.9 یا جدیدتر لازم است."
ok "پیش‌نیازها آماده‌اند (Agent وابستگی pip ندارد)."

step 3 "ساخت کاربر و مسیرها..."
if ! id -u "$AGENT_USER" >/dev/null 2>&1; then
  useradd --system --home-dir "$AGENT_HOME" --shell /usr/sbin/nologin "$AGENT_USER"
  ok "کاربر $AGENT_USER ساخته شد."
else
  ok "کاربر $AGENT_USER از قبل وجود دارد."
fi
mkdir -p "$AGENT_HOME" "$AGENT_CONF_DIR/tls" "$AGENT_STATE_DIR/build" "$AGENT_STATE_DIR/backup" \
         "$AGENT_LOG_DIR" "$TUNNEL_DIR" "$BINARY_DIR"
# مهم: پوشه conf هم باید مال alfa-agent باشد تا بتواند agent.env را بخواند
chown -R "$AGENT_USER:$AGENT_USER" \
  "$AGENT_HOME" "$AGENT_CONF_DIR" "$AGENT_STATE_DIR" "$AGENT_LOG_DIR" "$TUNNEL_DIR" "$BINARY_DIR"
chmod 750 "$AGENT_CONF_DIR" "$AGENT_STATE_DIR" "$TUNNEL_DIR" "$BINARY_DIR"
ok "مسیرها آماده شدند."

step 4 "کپی کدهای Agent..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC=""
for candidate in "$SCRIPT_DIR/../agent" "$SCRIPT_DIR/agent" "/opt/alfa-panel/agent"; do
  [[ -d "$candidate/alfa_agent" ]] && SRC="$candidate" && break
done
if [[ -z "$SRC" ]]; then
  [[ -n "$PANEL_URL" ]] || die "کد Agent پیدا نشد و آدرس پنل هم داده نشده است."
  TMP="$(mktemp -d)"
  log "دریافت بسته Agent از پنل..."
  curl -fsSLk "$PANEL_URL/agent-bundle.tar.gz" -o "$TMP/agent.tar.gz" \
    || die "دریافت بسته Agent از $PANEL_URL ناموفق بود."
  tar -xzf "$TMP/agent.tar.gz" -C "$TMP"
  SRC="$TMP/agent"
  [[ -d "$SRC/alfa_agent" ]] || die "بسته Agent ساختار مورد انتظار را ندارد."
fi
rm -rf "$AGENT_HOME/alfa_agent"
cp -r "$SRC/alfa_agent" "$AGENT_HOME/"
chown -R "$AGENT_USER:$AGENT_USER" "$AGENT_HOME"
find "$AGENT_HOME" -type f -name '*.py' -exec chmod 640 {} \;
ok "کدهای Agent در $AGENT_HOME نصب شدند."

step 5 "دریافت باندل تونل‌های داخلی پنل..."
if [[ -n "$PANEL_URL" ]]; then
  ASSET_TMP="$(mktemp -d)"
  if curl -fsSLk "$PANEL_URL/tunnel-assets.tar.gz" -o "$ASSET_TMP/tunnel-assets.tar.gz"; then
    mkdir -p "$BINARY_DIR"
    tar -xzf "$ASSET_TMP/tunnel-assets.tar.gz" -C "$ASSET_TMP"
    ASSET_ROOT="$ASSET_TMP/tunnel-assets"
    cp -f "$ASSET_ROOT/backhaul.sh" "$BINARY_DIR/backhaul.sh" 2>/dev/null || true
    cp -f "$ASSET_ROOT/backhaul_premium" "$BINARY_DIR/backhaul_premium" 2>/dev/null || true
    chmod 750 "$BINARY_DIR/backhaul.sh" "$BINARY_DIR/backhaul_premium" 2>/dev/null || true
    if [[ -f "$ASSET_ROOT/BrokenNode.tar.gz" ]]; then
      mkdir -p "$BINARY_DIR/brokennode-src"
      tar -xzf "$ASSET_ROOT/BrokenNode.tar.gz" -C "$BINARY_DIR/brokennode-src"
      case "$(uname -m)" in
        x86_64|amd64) BN_ARCH=amd64 ;;
        aarch64|arm64) BN_ARCH=arm64 ;;
        *) BN_ARCH=amd64 ;;
      esac
      if [[ -f "$BINARY_DIR/brokennode-src/BrokenNode/brokennode-linux-$BN_ARCH" ]]; then
        install -m 0750 "$BINARY_DIR/brokennode-src/BrokenNode/brokennode-linux-$BN_ARCH" "$BINARY_DIR/brokennode"
      fi
    fi
    chown -R "$AGENT_USER:$AGENT_USER" "$BINARY_DIR"
    ok "باندل تونل‌های داخلی آماده شد."
  else
    warn "باندل تونل‌های داخلی دریافت نشد؛ Repositoryها همچنان از داخل پنل قابل نصب هستند."
  fi
  rm -rf "$ASSET_TMP" 2>/dev/null || true
fi

step 6 "ساخت گواهی TLS محلی Agent..."
if [[ ! -f "$AGENT_CONF_DIR/tls/agent.crt" ]]; then
  openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
    -keyout "$AGENT_CONF_DIR/tls/agent.key" -out "$AGENT_CONF_DIR/tls/agent.crt" \
    -subj "/CN=$(hostname -f 2>/dev/null || hostname)" >/dev/null 2>&1
  ok "گواهی TLS ساخته شد."
else
  ok "گواهی TLS از قبل موجود است."
fi
chown -R "$AGENT_USER:$AGENT_USER" "$AGENT_CONF_DIR/tls"
chmod 600 "$AGENT_CONF_DIR/tls/agent.key"
chmod 644 "$AGENT_CONF_DIR/tls/agent.crt"

step 7 "نوشتن فایل تنظیمات..."
# مطمئن شو پوشه conf قابل دسترسی برای Agent است
chown -R "$AGENT_USER:$AGENT_USER" "$AGENT_CONF_DIR"
chmod 750 "$AGENT_CONF_DIR"

if [[ ! -f "$AGENT_CONF_DIR/agent.env" ]]; then
  cat >"$AGENT_CONF_DIR/agent.env" <<CONF
# تنظیمات Agent — Alfa VpnTunnel Managment
PANEL_URL=${PANEL_URL}
AGENT_HOST=0.0.0.0
AGENT_PORT=${AGENT_PORT}
AGENT_USE_TLS=true
AGENT_TLS_CERT=${AGENT_CONF_DIR}/tls/agent.crt
AGENT_TLS_KEY=${AGENT_CONF_DIR}/tls/agent.key
HEARTBEAT_INTERVAL=15
METRICS_INTERVAL=20
LOG_LEVEL=INFO
VERIFY_PANEL_TLS=false
PYTHONPATH=${AGENT_HOME}
CONF
else
  sed -i "s|^AGENT_PORT=.*|AGENT_PORT=${AGENT_PORT}|" "$AGENT_CONF_DIR/agent.env"
  [[ -n "$PANEL_URL" ]] && sed -i "s|^PANEL_URL=.*|PANEL_URL=${PANEL_URL}|" "$AGENT_CONF_DIR/agent.env"
fi
grep -q '^PYTHONPATH=' "$AGENT_CONF_DIR/agent.env" || echo "PYTHONPATH=${AGENT_HOME}" >>"$AGENT_CONF_DIR/agent.env"
# اگر PANEL_URL خالی مانده بود، حتماً ست شود
if [[ -n "$PANEL_URL" ]]; then
  if grep -qE '^PANEL_URL=' "$AGENT_CONF_DIR/agent.env"; then
    sed -i "s|^PANEL_URL=.*|PANEL_URL=${PANEL_URL}|" "$AGENT_CONF_DIR/agent.env"
  else
    echo "PANEL_URL=${PANEL_URL}" >>"$AGENT_CONF_DIR/agent.env"
  fi
fi
chown -R "$AGENT_USER:$AGENT_USER" "$AGENT_CONF_DIR"
chmod 600 "$AGENT_CONF_DIR/agent.env"
ok "تنظیمات نوشته شد: $AGENT_CONF_DIR/agent.env"

step 8 "نصب سرویس systemd و دسترسی محدود sudo..."
UNIT_SRC=""
for candidate in "$SRC/../agent/systemd" "$SCRIPT_DIR/../agent/systemd" "$SRC/systemd"; do
  [[ -f "$candidate/alfa-agent.service" ]] && UNIT_SRC="$candidate" && break
done
if [[ -n "$UNIT_SRC" ]]; then
  install -m 644 "$UNIT_SRC/alfa-agent.service" /etc/systemd/system/alfa-agent.service
  install -m 440 "$UNIT_SRC/alfa-agent.sudoers" /etc/sudoers.d/alfa-agent
else
  warn "فایل سرویس در بسته نبود؛ نسخه داخلی ساخته می‌شود."
  cat >/etc/systemd/system/alfa-agent.service <<UNIT
[Unit]
Description=Alfa VpnTunnel Managment Agent
After=network-online.target
[Service]
Type=simple
User=$AGENT_USER
EnvironmentFile=$AGENT_CONF_DIR/agent.env
WorkingDirectory=$AGENT_HOME
ExecStart=/usr/bin/python3 -m alfa_agent.main --serve
Restart=always
RestartSec=5
NoNewPrivileges=yes
PrivateTmp=yes
[Install]
WantedBy=multi-user.target
UNIT
fi
visudo -cf /etc/sudoers.d/alfa-agent >/dev/null 2>&1 || warn "بررسی فایل sudoers با هشدار همراه بود."
systemctl daemon-reload
ok "سرویس alfa-agent آماده است."

step 9 "ثبت Agent در پنل..."
if (( UPGRADE == 1 )); then
  ok "حالت به‌روزرسانی: مرحله ثبت‌نام رد شد."
elif [[ -f "$AGENT_STATE_DIR/state.json" ]] && grep -q '"agent_token"' "$AGENT_STATE_DIR/state.json"; then
  ok "این Agent قبلاً ثبت شده است؛ ثبت‌نام مجدد لازم نیست."
else
  [[ -n "$PANEL_URL" && -n "$TOKEN" ]] || die "برای ثبت‌نام هر دو مقدار --panel-url و --token لازم است."
  # PANEL_URL هم در env پاس داده می‌شود تا حتی اگر خواندن فایل مشکل داشت، مقدار موجود باشد
  if sudo -u "$AGENT_USER" env \
      PYTHONPATH="$AGENT_HOME" \
      ALFA_AGENT_ENV="$AGENT_CONF_DIR/agent.env" \
      PANEL_URL="$PANEL_URL" \
      python3 -m alfa_agent.main --register "$TOKEN"; then
    ok "ثبت‌نام در پنل انجام شد."
  else
    die "ثبت‌نام ناموفق بود. توکن یا آدرس پنل را بررسی کنید (توکن ۲۴ ساعت اعتبار دارد)."
  fi
fi

step 10 "تنظیم فایروال و اجرای سرویس..."
if (( NO_FIREWALL == 0 )) && command -v ufw >/dev/null 2>&1; then
  ufw allow "${AGENT_PORT}/tcp" >/dev/null 2>&1 || warn "تنظیم فایروال ناموفق بود."
  ok "پورت $AGENT_PORT در فایروال باز شد."
fi
systemctl enable alfa-agent >/dev/null 2>&1
systemctl restart alfa-agent
sleep 3
if systemctl is-active --quiet alfa-agent; then
  ok "سرویس alfa-agent فعال است."
else
  err "سرویس بالا نیامد. لاگ: journalctl -u alfa-agent -n 50 --no-pager"
  exit 1
fi

step 11 "تست اتصال..."
if curl -fsSk "https://127.0.0.1:${AGENT_PORT}/v1/health" >/dev/null 2>&1; then
  ok "Agent روی پورت $AGENT_PORT پاسخ می‌دهد."
else
  warn "پاسخ محلی دریافت نشد؛ اگر سرویس فعال است پورت/فایروال را بررسی کنید."
fi
sudo -u "$AGENT_USER" env PYTHONPATH="$AGENT_HOME" python3 -m alfa_agent.main --selftest || true

printf "\n%b\n" "${C_BOLD}========================================${C_RESET}"
printf "%b\n" " ${C_BOLD}Alfa Agent نصب شد${C_RESET}"
printf " Panel:    %s\n" "${PANEL_URL:-(تنظیم نشده)}"
printf " Port:     %s\n" "$AGENT_PORT"
printf " Service:  %s\n" "alfa-agent.service"
printf " Config:   %s\n" "$AGENT_CONF_DIR/agent.env"
printf " Logs:     %s\n" "journalctl -u alfa-agent -f"
printf "%b\n\n" "${C_BOLD}========================================${C_RESET}"