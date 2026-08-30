#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
A="$ROOT/tunnel-assets"
[[ -f "$A/BrokenNode.tar.gz" ]] || { echo "BrokenNode.tar.gz missing"; exit 1; }
[[ -f "$A/backhaul.sh" ]] || { echo "backhaul.sh missing"; exit 1; }
[[ -f "$A/backhaul_premium" ]] || { echo "backhaul_premium missing"; exit 1; }
tar -tzf "$A/BrokenNode.tar.gz" >/dev/null
[[ -x "$A/backhaul_premium" ]] || chmod +x "$A/backhaul_premium"
echo "Tunnel assets OK"
