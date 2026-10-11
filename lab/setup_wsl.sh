#!/usr/bin/env bash
# One-time setup inside WSL Ubuntu for the ConeGuard demo lab and Internet-scale simulations.
# Run once from the Ubuntu terminal:  bash setup_wsl.sh   (asks for your Linux password once)
set -euo pipefail

echo "== switch Ubuntu package sources to HTTPS (captive portals such as campus Wi-Fi hijack plain HTTP)"
for f in /etc/apt/sources.list.d/ubuntu.sources /etc/apt/sources.list; do
    if [ -f "$f" ]; then
        sudo sed -i 's#http://\(archive\|security\|ports\)\.ubuntu\.com#https://\1.ubuntu.com#g' "$f"
    fi
done

echo "== system packages"
sudo apt-get update
sudo apt-get install -y ca-certificates curl git jq python3-venv python3-pip pypy3 pypy3-venv iputils-ping traceroute

echo "== Docker Engine"
if ! command -v docker >/dev/null; then
    curl -fsSL https://get.docker.com | sudo sh
fi
sudo usermod -aG docker "$USER"

echo "== containerlab"
if ! command -v containerlab >/dev/null; then
    curl -sL https://get.containerlab.dev | sudo bash
fi
# containerlab runs without sudo for members of clab_admins
if getent group clab_admins >/dev/null; then
    sudo usermod -aG clab_admins "$USER"
fi

echo
echo "Done. Close this terminal and run 'wsl --shutdown' in Windows PowerShell once,"
echo "then reopen Ubuntu so the new group memberships apply. Check with: docker run --rm hello-world"
