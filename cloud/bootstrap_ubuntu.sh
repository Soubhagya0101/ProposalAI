#!/usr/bin/env bash
set -euo pipefail

sudo apt-get update
sudo apt-get install -y ca-certificates curl git ufw

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
fi

sudo usermod -aG docker "$USER"
sudo systemctl enable --now docker

sudo ufw allow OpenSSH
sudo ufw allow 8770/tcp
sudo ufw --force enable

echo "Docker installed."
echo "Log out and back in if docker commands require sudo."
echo "Server public IPv4:"
curl -4 https://ifconfig.me || true
echo
