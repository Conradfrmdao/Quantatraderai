#!/usr/bin/env bash
# QuantatraderAI — One-shot VPS bootstrap
# Run as root on a fresh Ubuntu 24.04 Hetzner server:
#   bash <(curl -fsSL https://raw.githubusercontent.com/Conradfrmdao/Quantatraderai/main/scripts/setup-vps.sh)
set -euo pipefail

REPO="https://github.com/Conradfrmdao/Quantatraderai.git"
APP_DIR="/opt/quantatraderai"
DOMAIN="api.quantatraderai.com"

echo "==> [1/7] System update"
apt-get update -qq && apt-get upgrade -y -qq

echo "==> [2/7] Install Docker"
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker

echo "==> [3/7] Install Caddy"
apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | tee /etc/apt/sources.list.d/caddy-stable.list
apt-get update -qq && apt-get install -y caddy
mkdir -p /var/log/caddy

echo "==> [4/7] Clone repository"
if [ -d "$APP_DIR" ]; then
    git -C "$APP_DIR" pull
else
    git clone "$REPO" "$APP_DIR"
fi

echo "==> [5/7] Copy Caddyfile"
cp "$APP_DIR/Caddyfile" /etc/caddy/Caddyfile
systemctl reload caddy || systemctl restart caddy

echo "==> [6/7] Set up .env"
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    echo ""
    echo "  !! IMPORTANT: Edit $APP_DIR/.env with your real keys before continuing."
    echo "  Run:  nano $APP_DIR/.env"
    echo "  Then: bash $APP_DIR/scripts/deploy.sh"
    echo ""
else
    echo "  .env already exists — skipping copy."
fi

echo "==> [7/7] Install deploy script as system command"
ln -sf "$APP_DIR/scripts/deploy.sh" /usr/local/bin/qai-deploy
chmod +x "$APP_DIR/scripts/deploy.sh"

echo ""
echo "======================================================"
echo " Bootstrap complete!"
echo " Next steps:"
echo "   1. nano $APP_DIR/.env          (fill in your keys)"
echo "   2. qai-deploy                  (build + start the API)"
echo "   3. curl https://$DOMAIN/api/status"
echo "======================================================"
