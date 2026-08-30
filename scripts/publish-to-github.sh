#!/usr/bin/env bash
set -Eeuo pipefail

# اجرا از ریشه پروژه در VS Code:
#   bash scripts/publish-to-github.sh https://github.com/USERNAME/REPOSITORY.git

REMOTE_URL="${1:-}"
if [[ -z "$REMOTE_URL" ]]; then
  echo "Usage: bash scripts/publish-to-github.sh https://github.com/USERNAME/REPOSITORY.git"
  exit 2
fi

case "$REMOTE_URL" in
  https://github.com/*.git|git@github.com:*.git) ;;
  *) echo "Remote باید یک آدرس GitHub معتبر باشد." >&2; exit 2;;
esac

if [[ -n "$(git status --porcelain 2>/dev/null || true)" ]]; then
  echo "تغییرات محلی وجود دارد؛ در حال commit کردن آنها..."
  git add .
  git commit -m "Prepare Alfa VpnTunnel Management for deployment" || true
fi

git branch -M main
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REMOTE_URL"
else
  git remote add origin "$REMOTE_URL"
fi

git push -u origin main

echo
echo "GitHub repository is connected and pushed: $REMOTE_URL"
echo "Install on a panel server after the push:"
echo "  git clone $REMOTE_URL alfa-vpn-tunnel-management"
echo "  cd alfa-vpn-tunnel-management/installer"
echo "  sudo bash install.sh"
