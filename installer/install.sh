#!/usr/bin/env bash
# نصب کامل پنل Alfa VpnTunnel Managment روی Ubuntu 22.04/24.04 و Debian 12
# اجرا:  sudo bash install.sh            (تعاملی)
#        sudo bash install.sh --non-interactive --domain panel.example.com --email you@example.com
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=lib-common.sh
source "$SCRIPT_DIR/lib-common.sh"

TOTAL=12
NON_INTERACTIVE=0
DOMAIN=""
EMAIL=""
PANEL_PORT_IN=""
ENABLE_HTTPS=""
ADMIN_USER="admin"
INSTALL_STARTED=0

usage() {
  cat <<'USAGE'
استفاده: sudo bash install.sh [گزینه‌ها]

  --non-interactive        بدون پرسش (از مقادیر پیش‌فرض/پارامترها استفاده می‌کند)
  --domain <dom>           دامنه پنل (برای HTTPS با Let's Encrypt)
  --email <mail>           ایمیل صدور گواهی
  --port <port>            پورت پنل (پیش‌فرض 8080 روی HTTP، 443 با دامنه)
  --admin <user>           نام کاربری مدیر (پیش‌فرض admin)
  --https                  فعال کردن HTTPS (نیازمند دامنه)
  --no-https               غیرفعال کردن HTTPS
  --dir <path>             مسیر نصب (پیش‌فرض /opt/alfa-panel)
  -h, --help               همین راهنما
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --non-interactive) NON_INTERACTIVE=1; shift ;;
    --domain) DOMAIN="${2:-}"; shift 2 ;;
    --email) EMAIL="${2:-}"; shift 2 ;;
    --port) PANEL_PORT_IN="${2:-}"; shift 2 ;;
    --admin) ADMIN_USER="${2:-admin}"; shift 2 ;;
    --https) ENABLE_HTTPS=1; shift ;;
    --no-https) ENABLE_HTTPS=0; shift ;;
    --dir) ALFA_DIR="${2:-}"; ALFA_ENV="$ALFA_DIR/.env"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) warn "گزینه ناشناخته: $1"; shift ;;
  esac
done

rollback() {
  local code=$?
  if (( code != 0 )) && (( INSTALL_STARTED == 1 )); then
    err "نصب با خطا متوقف شد. در حال بازگردانی سرویس‌ها..."
    compose down --remove-orphans >/dev/null 2>&1 || true
    warn "فایل‌های نصب در $ALFA_DIR باقی مانده‌اند تا بتوانید لاگ را بررسی کنید:"
    warn "  $ALFA_LOG_FILE"
    warn "برای تلاش مجدد همین اسکریپت را دوباره اجرا کنید (idempotent است)."
  fi
  exit $code
}
trap rollback EXIT

require_root
log_init
banner
info "لاگ نصب: $ALFA_LOG_FILE"

# ---------------------------------------------------------------- 1
step 1 $TOTAL "بررسی سیستم..."
detect_os
detect_arch
check_internet
check_dns
check_resources 1500 5
check_time_sync

# ---------------------------------------------------------------- 2
step 2 $TOTAL "دریافت تنظیمات نصب..."
if (( NON_INTERACTIVE == 0 )); then
  read -rp "دامنه پنل (خالی = دسترسی با IP): " ans_domain || true
  DOMAIN="${ans_domain:-$DOMAIN}"
  if [[ -n "$DOMAIN" ]]; then
    read -rp "ایمیل برای گواهی Let's Encrypt: " ans_email || true
    EMAIL="${ans_email:-$EMAIL}"
    read -rp "فعال کردن HTTPS؟ [Y/n]: " ans_https || true
    [[ "${ans_https:-Y}" =~ ^[Nn] ]] && ENABLE_HTTPS=0 || ENABLE_HTTPS=1
  else
    ENABLE_HTTPS=0
  fi
  read -rp "پورت پنل [${PANEL_PORT_IN:-8080}]: " ans_port || true
  PANEL_PORT_IN="${ans_port:-${PANEL_PORT_IN:-8080}}"
  read -rp "نام کاربری مدیر [$ADMIN_USER]: " ans_admin || true
  ADMIN_USER="${ans_admin:-$ADMIN_USER}"
  log "${C_DIM}پسورد مدیر به صورت تصادفی و امن ساخته می‌شود.${C_RESET}"
fi
PANEL_PORT="${PANEL_PORT_IN:-8080}"
[[ -z "$ENABLE_HTTPS" ]] && ENABLE_HTTPS=0
if (( ENABLE_HTTPS == 1 )) && [[ -z "$DOMAIN" ]]; then
  warn "برای HTTPS دامنه لازم است؛ HTTPS غیرفعال شد."
  ENABLE_HTTPS=0
fi
if (( ENABLE_HTTPS == 1 )); then HTTP_PORT=80; HTTPS_PORT=443; else HTTP_PORT="$PANEL_PORT"; HTTPS_PORT=8443; fi
check_ports "$HTTP_PORT" || warn "در صورت تداخل پورت، با --port پورت دیگری بدهید."

# ---------------------------------------------------------------- 3
step 3 $TOTAL "نصب پیش‌نیازها..."
export DEBIAN_FRONTEND=noninteractive
run apt-get update -y
run apt-get install -y ca-certificates curl gnupg openssl git ufw jq iproute2 rsync
ok "بسته‌های پایه نصب شدند."

if ! command -v docker >/dev/null 2>&1; then
  info "نصب Docker..."
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/${OS_ID}/gpg" -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$ARCH signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${OS_ID} $(. /etc/os-release && echo "${VERSION_CODENAME}") stable" \
    >/etc/apt/sources.list.d/docker.list
  run apt-get update -y
  run apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  run systemctl enable --now docker
  ok "Docker نصب شد."
else
  ok "Docker از قبل نصب است: $(docker --version)"
  docker compose version >/dev/null 2>&1 || run apt-get install -y docker-compose-plugin
fi

# ---------------------------------------------------------------- 4
step 4 $TOTAL "کپی فایل‌های پروژه به $ALFA_DIR ..."
INSTALL_STARTED=1
mkdir -p "$ALFA_DIR" "$ALFA_DATA" "$ALFA_DATA/backups" /opt/alfa/tunnel-binaries "$ALFA_LOG_DIR"
run rsync -a --delete \
  --exclude '.git' --exclude 'node_modules' --exclude 'frontend/dist' --exclude '__pycache__' \
  "$REPO_ROOT/" "$ALFA_DIR/"
chmod 750 "$ALFA_DIR"
ok "فایل‌ها کپی شدند."

# ---------------------------------------------------------------- 5
step 5 $TOTAL "ساخت Secretهای امن و فایل .env ..."
if [[ ! -f "$ALFA_ENV" ]]; then
  cp "$ALFA_DIR/.env.example" "$ALFA_ENV"
  chmod 600 "$ALFA_ENV"
  ok "فایل .env از نمونه ساخته شد."
else
  ok "فایل .env موجود بود؛ مقادیر قبلی حفظ می‌شوند."
fi

[[ -n "$(env_get SECRET_KEY)" && "$(env_get SECRET_KEY)" != "change-me" ]] || env_set SECRET_KEY "$(gen_secret 64)"
[[ -n "$(env_get SECRETS_ENCRYPTION_KEY)" ]] || env_set SECRETS_ENCRYPTION_KEY "$(gen_secret 64)"
[[ -n "$(env_get POSTGRES_PASSWORD)" && "$(env_get POSTGRES_PASSWORD)" != "change-me" ]] || env_set POSTGRES_PASSWORD "$(gen_secret 32)"

env_set ENVIRONMENT production
env_set DEBUG false
env_set PANEL_PORT "$PANEL_PORT"
env_set HTTP_PORT "$HTTP_PORT"
env_set HTTPS_PORT "${HTTPS_PORT}"
env_set ALFA_DATA "$ALFA_DATA"
env_set PANEL_DOMAIN "${DOMAIN}"
env_set LETSENCRYPT_EMAIL "${EMAIL}"
env_set ENABLE_HTTPS "$([[ $ENABLE_HTTPS -eq 1 ]] && echo true || echo false)"
env_set COOKIE_SECURE "$([[ $ENABLE_HTTPS -eq 1 ]] && echo true || echo false)"
SERVER_IP="$(curl -fsS --max-time 6 https://api.ipify.org 2>/dev/null || hostname -I | awk '{print $1}')"
if (( ENABLE_HTTPS == 1 )); then
  PANEL_URL="https://$DOMAIN"
elif [[ "$HTTP_PORT" == "80" ]]; then
  PANEL_URL="http://$SERVER_IP"
else
  PANEL_URL="http://$SERVER_IP:$HTTP_PORT"
fi
env_set PANEL_URL "$PANEL_URL"
ok "Secretها ساخته و تنظیمات ذخیره شد."

# ---------------------------------------------------------------- 6
step 6 $TOTAL "آماده‌سازی Reverse Proxy و گواهی..."
mkdir -p "$ALFA_DIR/deploy/nginx/conf.d" "$ALFA_DATA/certs" "$ALFA_DATA/acme"
if (( ENABLE_HTTPS == 1 )); then
  sed -e "s|__DOMAIN__|$DOMAIN|g" "$ALFA_DIR/deploy/nginx/panel-https.conf.template" \
    >"$ALFA_DIR/deploy/nginx/conf.d/panel.conf"
  if [[ ! -f "$ALFA_DATA/certs/fullchain.pem" ]]; then
    info "صدور گواهی Let's Encrypt برای $DOMAIN ..."
    run apt-get install -y certbot
    if certbot certonly --standalone --non-interactive --agree-tos \
        -m "${EMAIL:-admin@$DOMAIN}" -d "$DOMAIN" >>"$ALFA_LOG_FILE" 2>&1; then
      cp -L "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" "$ALFA_DATA/certs/fullchain.pem"
      cp -L "/etc/letsencrypt/live/$DOMAIN/privkey.pem" "$ALFA_DATA/certs/privkey.pem"
      ok "گواهی صادر شد."
    else
      warn "صدور گواهی ناموفق بود؛ گواهی موقت self-signed ساخته می‌شود."
      openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout "$ALFA_DATA/certs/privkey.pem" -out "$ALFA_DATA/certs/fullchain.pem" \
        -subj "/CN=$DOMAIN" >>"$ALFA_LOG_FILE" 2>&1
    fi
  else
    ok "گواهی از قبل موجود است."
  fi
else
  sed -e "s|__PORT__|$HTTP_PORT|g" "$ALFA_DIR/deploy/nginx/panel-http.conf.template" \
    >"$ALFA_DIR/deploy/nginx/conf.d/panel.conf"
  ok "پنل روی HTTP سرو می‌شود (بدون دامنه)."
fi

# ---------------------------------------------------------------- 7
step 7 $TOTAL "ساخت و اجرای سرویس‌ها (Docker)..."
cd "$ALFA_DIR"
run compose pull --ignore-buildable || true
run compose build
run compose up -d
ok "کانتینرها اجرا شدند."

# ---------------------------------------------------------------- 8
step 8 $TOTAL "انتظار برای آماده شدن دیتابیس..."
for _ in $(seq 1 40); do
  if compose exec -T postgres pg_isready -U "$(env_get POSTGRES_USER)" >/dev/null 2>&1; then
    ok "PostgreSQL آماده است."; break
  fi
  sleep 3
done

# ---------------------------------------------------------------- 9
step 9 $TOTAL "اجرای Migrationهای دیتابیس..."
run compose exec -T backend alembic upgrade head
ok "دیتابیس به‌روزرسانی شد."

# ---------------------------------------------------------------- 10
step 10 $TOTAL "ساخت کاربر مدیر و پسورد تصادفی..."
ADMIN_OUTPUT="$(compose exec -T backend python -m app.cli create-admin --username "$ADMIN_USER" 2>&1 | tee -a "$ALFA_LOG_FILE")"
ADMIN_PASS="$(printf '%s' "$ADMIN_OUTPUT" | grep -E '^password:' | tail -1 | awk '{print $2}')"
if [[ -z "$ADMIN_PASS" ]]; then
  warn "کاربر مدیر از قبل وجود داشت؛ پسورد جدیدی ساخته نشد."
  warn "برای بازنشانی: cd $ALFA_DIR && docker compose exec backend python -m app.cli create-admin"
fi
ok "کاربر مدیر آماده است."

# ---------------------------------------------------------------- 11
step 11 $TOTAL "تنظیم فایروال و سرویس systemd..."
if command -v ufw >/dev/null 2>&1; then
  run ufw --force enable || true
  run ufw allow OpenSSH || run ufw allow 22/tcp || true
  if (( ENABLE_HTTPS == 1 )); then run ufw allow 80/tcp; run ufw allow 443/tcp
  else run ufw allow "${HTTP_PORT}/tcp"; fi
  ok "فایروال تنظیم شد (فقط پورت‌های لازم باز است)."
else
  warn "ufw موجود نیست؛ فایروال به صورت خودکار تنظیم نشد."
fi

cat >/etc/systemd/system/alfa-panel.service <<UNIT
[Unit]
Description=Alfa VpnTunnel Managment Panel (docker compose)
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$ALFA_DIR
ExecStart=/usr/bin/docker compose --env-file $ALFA_ENV up -d
ExecStop=/usr/bin/docker compose --env-file $ALFA_ENV down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
UNIT
run systemctl daemon-reload
run systemctl enable alfa-panel.service
ok "سرویس alfa-panel برای اجرای خودکار پس از ری‌استارت فعال شد."

# ---------------------------------------------------------------- 12
step 12 $TOTAL "بررسی سلامت نهایی..."
HEALTH_URL="http://127.0.0.1:${HTTP_PORT}/health"
(( ENABLE_HTTPS == 1 )) && HEALTH_URL="https://127.0.0.1/health"
if wait_for_http "$HEALTH_URL" 40; then
  ok "پنل پاسخ می‌دهد."
else
  err "پنل در زمان انتظار پاسخ نداد."
  err "برای بررسی: cd $ALFA_DIR && docker compose logs --tail 100"
  err "یا اجرای:  sudo bash $ALFA_DIR/installer/diagnose.sh"
  exit 1
fi

INSTALL_STARTED=0
trap - EXIT

printf "\n%b\n" "${C_BOLD}========================================${C_RESET}"
printf "%b\n" " ${C_BOLD}$ALFA_NAME${C_RESET}"
printf "%b\n" "${C_BOLD}========================================${C_RESET}"
printf " Panel URL:  %b\n" "${C_GREEN}${PANEL_URL}${C_RESET}"
printf " Username:   %b\n" "${C_GREEN}${ADMIN_USER}${C_RESET}"
if [[ -n "$ADMIN_PASS" ]]; then
  printf " Password:   %b\n" "${C_GREEN}${ADMIN_PASS}${C_RESET}"
else
  printf " Password:   %b\n" "${C_YELLOW}(کاربر از قبل وجود داشت)${C_RESET}"
fi
printf " Version:    %s\n" "1.0.0"
printf " Services:   %s\n" "backend, frontend(nginx), postgres, redis"
printf " Ports:      %s\n" "$([[ $ENABLE_HTTPS -eq 1 ]] && echo '80, 443' || echo "$HTTP_PORT")"
printf " Config:     %s\n" "$ALFA_ENV"
printf " Data:       %s\n" "$ALFA_DATA"
printf " Logs:       %s\n" "$ALFA_LOG_FILE"
printf "%b\n\n" "${C_BOLD}========================================${C_RESET}"
printf "%b\n" "این پسورد فقط همین یک بار نمایش داده می‌شود و در دیتابیس فقط hash آن ذخیره شده است."
printf "%b\n" "پس از اولین ورود، تغییر پسورد اجباری است."
printf "%b\n\n" "برای نصب Agent روی سرورها: از پنل ← سرورها ← افزودن سرور، دستور نصب را کپی کنید."
