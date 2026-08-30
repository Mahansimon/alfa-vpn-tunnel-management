# Alfa VpnTunnel Managment

پنل مدیریت فارسی و RTL برای مدیریت چند سرور لینوکسی، نصب Agent، ساخت و کنترل Tunnel، مانیتورینگ CPU/RAM/Disk/Network، حساب‌داری ترافیک، لاگ، هشدار، اعلان، RBAC، Audit Log، Backup و Update.

## Quick Start

### Development
```bash
# backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp ../.env.example .env
uvicorn app.main:app --reload --port 8000

# frontend
cd ../frontend
npm install
npm run dev
```

### Build
```bash
cd frontend && npm run build
cd ../backend && python -m compileall app
```

### Production Install
```bash
git clone YOUR_REAL_GITHUB_REPOSITORY_URL alfa-vpn-tunnel-management
cd alfa-vpn-tunnel-management/installer
sudo bash install.sh
```

### Production Install روی سرور ایران یا خارج
فرقی ندارد. همین دستور را روی سروری که پنل باید روی آن بالا بیاید اجرا کنید:
```bash
cd installer
sudo bash install.sh --domain your-panel.example.com --email you@example.com
```
اگر دامنه ندارید:
```bash
cd installer
sudo bash install.sh --no-https --port 8080
```

### Agent Install
بعد از Add Server در پنل، دستور آماده به شما داده می‌شود. شکل کلی:
```bash
curl -fsSL https://YOUR-PANEL/install-agent.sh -o install-agent.sh
sudo bash install-agent.sh --panel-url https://YOUR-PANEL --token YOUR_REGISTRATION_TOKEN
```

## محل وارد کردن Repository و Binary تونل‌ها
- از UI: `Settings -> tunnel` یا `Tunnel Types`
- از فایل: `.env`
- متغیرها:
  - `PACKET_TUNNEL_REPOSITORY`
  - `BACKPACK_REPOSITORY`
  - `PING_TUNNEL_REPOSITORY`
  - `RATHOLE_REPOSITORY`
  - `PREMIUM_BACKHAUL_BINARY`
  - `BROKEN_NODE_BINARY`

## محل قرار دادن Binaryهای Premium Backhaul و Broken Node
پیش‌فرض:
```bash
/opt/alfa/tunnel-binaries/
```
سپس مسیر کامل را در Settings یا `.env` وارد کنید.

## Login اولیه
Installer در پایان همین‌ها را روی ترمینال نمایش می‌دهد:
- `Panel URL`
- `Username`
- `Password`

پسورد خام فقط همان‌جا نشان داده می‌شود و در دیتابیس فقط hash آن ذخیره می‌شود.

## Troubleshooting
```bash
# وضعیت کلی
cd /opt/alfa-panel && docker compose ps
cd /opt/alfa-panel && docker compose exec backend python -m app.cli status

# لاگ‌ها
cd /opt/alfa-panel && docker compose logs -f backend
journalctl -u alfa-agent -f

# ری‌استارت
sudo systemctl restart alfa-panel
sudo systemctl restart alfa-agent

# تعمیر
sudo bash /opt/alfa-panel/installer/repair.sh

# تشخیص
sudo bash /opt/alfa-panel/installer/diagnose.sh
```

## ساختار پروژه
```text
alfa-vpn-tunnel-management/
├── frontend/
├── backend/
├── agent/
├── installer/
├── deploy/
├── docker/
├── docs/
├── scripts/
├── .github/workflows/
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── README.md
└── LICENSE
```

## GitHub Push
```bash
git init
git add .
git commit -m "Initial commit: Alfa VpnTunnel Managment"
git branch -M main
git remote add origin YOUR_REAL_GITHUB_REPOSITORY_URL
git push -u origin main
```

## وضعیت Adapterهای تونل
- **BackPack**: از Repository و Release/Build پشتیبانی می‌کند؛ ساختار Go ریشه پروژه شناسایی می‌شود.
- **Paqet**: Repository و Build از `./cmd` پشتیبانی می‌شود؛ این پروژه در README خود هشدار می‌دهد که در حال توسعه است.
- **PingTunnel**: Binary از Release رسمی PingTunnel برای amd64/arm64 تهیه و سرویس systemd ساخته می‌شود؛ تنظیمات نقش client/server از پنل ارسال می‌شود.
- **Rathole 2**: Binary amd64 از core موجود در Repository داده‌شده تهیه می‌شود و config TOML تک‌سرویس از مقادیر پنل ساخته می‌شود.
- **BrokenNode / Premium Backhaul**: باندل‌های ارسالی شما همراه پنل ارائه می‌شوند.

برای Binaryها و Repositoryها فقط منابعی را اجرا کنید که به آن‌ها اعتماد دارید. Secretها را هرگز داخل Git commit نکنید.
