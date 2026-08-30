#!/usr/bin/env bash
# توابع مشترک اسکریپت‌های نصب/تعمیر/تشخیص Alfa VpnTunnel Managment
set -o pipefail

ALFA_NAME="Alfa VpnTunnel Managment"
ALFA_DIR="${ALFA_DIR:-/opt/alfa-panel}"
ALFA_DATA="${ALFA_DATA:-/var/lib/alfa}"
ALFA_LOG_DIR="${ALFA_LOG_DIR:-/var/log/alfa}"
ALFA_ENV="$ALFA_DIR/.env"

C_RESET='\033[0m'; C_DIM='\033[2m'; C_RED='\033[1;31m'; C_GREEN='\033[1;32m'
C_YELLOW='\033[1;33m'; C_BLUE='\033[1;36m'; C_BOLD='\033[1m'

log_init() {
  mkdir -p "$ALFA_LOG_DIR"
  ALFA_LOG_FILE="${ALFA_LOG_FILE:-$ALFA_LOG_DIR/install-$(date +%Y%m%d-%H%M%S).log}"
  touch "$ALFA_LOG_FILE"
  chmod 600 "$ALFA_LOG_FILE"
}

log()   { printf "%b\n" "$*" | tee -a "${ALFA_LOG_FILE:-/dev/null}" >&2; }
info()  { log "${C_BLUE}▸${C_RESET} $*"; }
ok()    { log "${C_GREEN}✔${C_RESET} $*"; }
warn()  { log "${C_YELLOW}!${C_RESET} $*"; }
err()   { log "${C_RED}✘${C_RESET} $*"; }
step()  { log "\n${C_BOLD}[$1/$2]${C_RESET} $3"; }
die()   { err "$*"; exit 1; }

# اجرای دستور با ثبت خروجی در لاگ (خروجی روی صفحه خلاصه می‌ماند)
run() {
  log "${C_DIM}\$ $*${C_RESET}"
  if ! "$@" >>"${ALFA_LOG_FILE:-/dev/null}" 2>&1; then
    err "اجرای دستور ناموفق بود: $*"
    err "جزئیات کامل در ${ALFA_LOG_FILE:-لاگ} ثبت شده است."
    return 1
  fi
  return 0
}

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    die "این اسکریپت باید با دسترسی root اجرا شود. از «sudo bash $0» استفاده کنید."
  fi
}

detect_os() {
  [[ -r /etc/os-release ]] || die "سیستم‌عامل قابل تشخیص نیست (/etc/os-release یافت نشد)."
  # shellcheck disable=SC1091
  . /etc/os-release
  OS_ID="${ID:-unknown}"; OS_VERSION="${VERSION_ID:-0}"; OS_NAME="${PRETTY_NAME:-$OS_ID}"
  case "$OS_ID" in
    ubuntu)
      case "$OS_VERSION" in
        22.04|24.04) ok "سیستم‌عامل پشتیبانی‌شده: $OS_NAME" ;;
        *) warn "Ubuntu $OS_VERSION رسماً تست نشده است (هدف: 22.04 و 24.04). ادامه با ریسک شما." ;;
      esac ;;
    debian)
      case "$OS_VERSION" in
        12) ok "سیستم‌عامل پشتیبانی‌شده: $OS_NAME" ;;
        *) warn "Debian $OS_VERSION رسماً تست نشده است (هدف: 12)." ;;
      esac ;;
    *) warn "توزیع «$OS_NAME» رسماً پشتیبانی نمی‌شود؛ فقط Ubuntu 22.04/24.04 و Debian 12 تست شده‌اند." ;;
  esac
}

detect_arch() {
  ARCH_RAW="$(uname -m)"
  case "$ARCH_RAW" in
    x86_64|amd64) ARCH="amd64" ;;
    aarch64|arm64) ARCH="arm64" ;;
    *) die "معماری «$ARCH_RAW» پشتیبانی نمی‌شود. فقط amd64 و arm64 پشتیبانی می‌شوند." ;;
  esac
  ok "معماری CPU: $ARCH"
}

check_internet() {
  if command -v curl >/dev/null 2>&1; then
    curl -fsS --max-time 8 https://deb.debian.org >/dev/null 2>&1 && { ok "اتصال اینترنت برقرار است."; return 0; }
    curl -fsS --max-time 8 https://github.com >/dev/null 2>&1 && { ok "اتصال اینترنت برقرار است."; return 0; }
  fi
  ping -c1 -W3 1.1.1.1 >/dev/null 2>&1 && { warn "دسترسی HTTPS محدود است اما شبکه فعال است."; return 0; }
  die "اتصال اینترنت برقرار نیست. نصب بدون اینترنت ممکن نیست."
}

check_dns() {
  if command -v getent >/dev/null 2>&1 && getent hosts github.com >/dev/null 2>&1; then
    ok "DNS سالم است."
  else
    warn "DNS پاسخ نمی‌دهد. اگر نصب متوقف شد، /etc/resolv.conf را بررسی کنید."
  fi
}

check_resources() {
  local min_ram_mb="${1:-1500}" min_disk_gb="${2:-5}"
  local ram_mb disk_gb
  ram_mb=$(( $(awk '/MemTotal/ {print $2}' /proc/meminfo) / 1024 ))
  disk_gb=$(df -BG --output=avail / | tail -1 | tr -dc '0-9')
  if (( ram_mb < min_ram_mb )); then
    warn "حجم RAM (${ram_mb}MB) کمتر از حد پیشنهادی (${min_ram_mb}MB) است."
  else
    ok "RAM کافی است: ${ram_mb}MB"
  fi
  if (( disk_gb < min_disk_gb )); then
    die "فضای دیسک کافی نیست: ${disk_gb}GB آزاد، حداقل ${min_disk_gb}GB لازم است."
  fi
  ok "فضای دیسک کافی است: ${disk_gb}GB آزاد"
}

check_time_sync() {
  if command -v timedatectl >/dev/null 2>&1; then
    if timedatectl show -p NTPSynchronized --value 2>/dev/null | grep -qi yes; then
      ok "زمان سیستم با NTP همگام است."
    else
      warn "زمان سیستم همگام نیست. برای صحت توکن‌ها اجرا کنید: timedatectl set-ntp true"
    fi
  fi
}

port_in_use() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -lntH "( sport = :$port )" 2>/dev/null | grep -q . && return 0
  fi
  return 1
}

check_ports() {
  local conflict=0
  for port in "$@"; do
    if port_in_use "$port"; then warn "پورت $port در حال استفاده است."; conflict=1
    else ok "پورت $port آزاد است."; fi
  done
  return $conflict
}

gen_secret() {
  local length="${1:-48}"
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 $((length * 2)) | tr -dc 'A-Za-z0-9' | head -c "$length"
  else
    tr -dc 'A-Za-z0-9' </dev/urandom | head -c "$length"
  fi
}

gen_password() {
  # پسورد امن: حروف بزرگ/کوچک/عدد/کاراکتر ویژه، حداقل ۲۴ کاراکتر
  local length="${1:-24}" pass=""
  local upper lower digit special rest
  upper=$(tr -dc 'A-Z' </dev/urandom | head -c2)
  lower=$(tr -dc 'a-z' </dev/urandom | head -c2)
  digit=$(tr -dc '0-9' </dev/urandom | head -c2)
  special=$(tr -dc '!@#%^*_-+=?' </dev/urandom | head -c2)
  rest=$(tr -dc 'A-Za-z0-9!@#%^*_-+=?' </dev/urandom | head -c $((length - 8)))
  pass="${upper}${lower}${digit}${special}${rest}"
  # به‌هم‌ریختن ترتیب
  printf '%s' "$pass" | fold -w1 | shuf | tr -d '\n'
}

env_get() {
  local key="$1" file="${2:-$ALFA_ENV}"
  [[ -f "$file" ]] || return 1
  grep -E "^${key}=" "$file" | tail -1 | cut -d= -f2- | tr -d '"'
}

env_set() {
  local key="$1" value="$2" file="${3:-$ALFA_ENV}"
  touch "$file"
  if grep -qE "^${key}=" "$file"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$file"
  else
    printf '%s=%s\n' "$key" "$value" >>"$file"
  fi
}

compose() {
  if docker compose version >/dev/null 2>&1; then
    docker compose -f "$ALFA_DIR/docker-compose.yml" --env-file "$ALFA_ENV" "$@"
  else
    docker-compose -f "$ALFA_DIR/docker-compose.yml" --env-file "$ALFA_ENV" "$@"
  fi
}

wait_for_http() {
  local url="$1" tries="${2:-40}" i=0
  while (( i < tries )); do
    if curl -fsk --max-time 5 "$url" >/dev/null 2>&1; then return 0; fi
    sleep 3; i=$((i+1))
  done
  return 1
}

banner() {
  printf "\n%b\n" "${C_BOLD}========================================${C_RESET}"
  printf "%b\n" "  ${C_BOLD}$ALFA_NAME${C_RESET}"
  printf "%b\n\n" "${C_BOLD}========================================${C_RESET}"
}
