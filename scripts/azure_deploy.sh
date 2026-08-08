#!/usr/bin/env bash
# Provisions a split-VM Azure deployment: one VM runs the shared MCP
# capability containers (WolframAlpha, Playwright, research_pack, dev_pack,
# and Ollama if used), the other runs this backend plus the per-agent
# containers it creates on demand. The two talk to each other over a
# private VNet — the backend manages the capabilities VM's Docker daemon
# remotely over SSH (CAPABILITIES_DOCKER_HOST), and capability containers
# are addressed by private IP + published port at runtime
# (CAPABILITIES_HOST), since container-name DNS only resolves within one
# Docker daemon's own network. See backend/app/mcp_manager.py for the
# corresponding code.
#
# Prerequisites: `az login` already done, an SSH keypair at
# ~/.ssh/forge_ai_azure (generate with `ssh-keygen -t ed25519 -f
# ~/.ssh/forge_ai_azure -N ""` if it doesn't exist), and backend/.env
# filled in locally (its real values get copied to the agents VM).
#
# A real wrinkle hit provisioning this the first time: Standard_B-series
# VMs (the usual cheap default) came back "SkuNotAvailable... Capacity
# Restrictions" on every region tried — turned out to be two separate
# issues, not a genuine capacity shortage: (1) Microsoft.Compute wasn't
# registered as a resource provider on the subscription yet (`az provider
# register --namespace Microsoft.Compute` fixes this, takes a couple
# minutes), and (2) even after that, B-series specifically was
# NotAvailableForSubscription for this particular subscription tier —
# `az vm list-skus --location <region> --resource-type virtualMachines`
# and checking each SKU's `restrictions` field is how to find one that
# actually is available. Standard_D2s_v7 worked here; it may not be the
# right one for a different subscription.
set -euo pipefail

RG="${RG:-forge-ai-rg}"
LOCATION="${LOCATION:-eastus}"
VM_SIZE="${VM_SIZE:-Standard_D2s_v7}"
VNET="${VNET:-forge-vnet}"
SUBNET="${SUBNET:-forge-subnet}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/forge_ai_azure}"
ADMIN_USER="azureuser"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

command -v az >/dev/null || { echo "az CLI is required — see https://aka.ms/installazurecliwindows"; exit 1; }
[ -f "$SSH_KEY" ] || { echo "Generate a keypair first: ssh-keygen -t ed25519 -f $SSH_KEY -N ''"; exit 1; }
[ -f "$ROOT_DIR/backend/.env" ] || { echo "backend/.env is missing — set it up (see .env.example) before deploying"; exit 1; }

echo "==> Resource group"
az group create --name "$RG" --location "$LOCATION" -o none

echo "==> VNet + NSGs"
az network vnet create --resource-group "$RG" --name "$VNET" --location "$LOCATION" \
  --address-prefix 10.0.0.0/16 --subnet-name "$SUBNET" --subnet-prefix 10.0.0.0/24 -o none

MY_IP="$(curl -s -4 https://ifconfig.me)"

az network nsg create --resource-group "$RG" --name forge-cap-nsg --location "$LOCATION" -o none
az network nsg rule create --resource-group "$RG" --nsg-name forge-cap-nsg --name allow-ssh \
  --priority 100 --access Allow --protocol Tcp --destination-port-ranges 22 \
  --source-address-prefixes 10.0.0.0/16 "$MY_IP/32" -o none

az network nsg create --resource-group "$RG" --name forge-agents-nsg --location "$LOCATION" -o none
az network nsg rule create --resource-group "$RG" --nsg-name forge-agents-nsg --name allow-ssh \
  --priority 100 --access Allow --protocol Tcp --destination-port-ranges 22 \
  --source-address-prefixes "$MY_IP/32" -o none
az network nsg rule create --resource-group "$RG" --nsg-name forge-agents-nsg --name allow-backend-api \
  --priority 110 --access Allow --protocol Tcp --destination-port-ranges 8000 \
  --source-address-prefixes "*" -o none

echo "==> Capabilities VM"
cat > /tmp/forge-cloudinit-capabilities.yaml <<'EOF'
#cloud-config
package_update: true
runcmd:
  - curl -fsSL https://get.docker.com | sh
  - usermod -aG docker azureuser
  - systemctl enable docker
  - systemctl start docker
EOF
az vm create --resource-group "$RG" --name forge-capabilities-vm --image Ubuntu2204 \
  --size "$VM_SIZE" --location "$LOCATION" --vnet-name "$VNET" --subnet "$SUBNET" \
  --nsg forge-cap-nsg --admin-username "$ADMIN_USER" --ssh-key-values "$SSH_KEY.pub" \
  --custom-data /tmp/forge-cloudinit-capabilities.yaml --public-ip-sku Standard -o none

echo "==> Agents VM"
az vm create --resource-group "$RG" --name forge-agents-vm --image Ubuntu2204 \
  --size "$VM_SIZE" --location "$LOCATION" --vnet-name "$VNET" --subnet "$SUBNET" \
  --nsg forge-agents-nsg --admin-username "$ADMIN_USER" --ssh-key-values "$SSH_KEY.pub" \
  --public-ip-sku Standard -o none

CAP_PRIVATE_IP="$(az vm show -d --resource-group "$RG" --name forge-capabilities-vm --query privateIps -o tsv)"
AGENTS_PUBLIC_IP="$(az vm show -d --resource-group "$RG" --name forge-agents-vm --query publicIps -o tsv)"
echo "Capabilities VM private IP: $CAP_PRIVATE_IP"
echo "Agents VM public IP: $AGENTS_PUBLIC_IP"

SSH="ssh -o StrictHostKeyChecking=accept-new -i $SSH_KEY $ADMIN_USER@$AGENTS_PUBLIC_IP"

echo "==> Waiting for capabilities VM's cloud-init (Docker install) to finish"
ssh -o StrictHostKeyChecking=accept-new -i "$SSH_KEY" "$ADMIN_USER@$CAP_PRIVATE_IP" \
  "cloud-init status --wait" 2>/dev/null || \
  ssh -o StrictHostKeyChecking=accept-new -i "$SSH_KEY" "$ADMIN_USER@$(az vm show -d --resource-group "$RG" --name forge-capabilities-vm --query publicIps -o tsv)" \
  "cloud-init status --wait"

echo "==> Provisioning the agents VM: Docker, Python, git, this repo"
$SSH "curl -fsSL https://get.docker.com | sudo sh && sudo usermod -aG docker $ADMIN_USER && \
  sudo apt-get update -qq && sudo apt-get install -y -qq python3-venv python3-pip git"
$SSH "git clone https://github.com/XytheRoblox/Forge-AI.git 2>/dev/null || (cd Forge-AI && git pull)"
$SSH "cd Forge-AI/backend && python3 -m venv .venv && ./.venv/bin/pip install --quiet --upgrade pip && ./.venv/bin/pip install --quiet -r requirements.txt"

echo "==> Wiring the agents VM to reach the capabilities VM over SSH"
scp -i "$SSH_KEY" "$SSH_KEY" "$SSH_KEY.pub" "$ADMIN_USER@$AGENTS_PUBLIC_IP:~/.ssh/"
$SSH "chmod 600 ~/.ssh/$(basename "$SSH_KEY")"
$SSH "cat > ~/.ssh/config <<EOF
Host $CAP_PRIVATE_IP
    User $ADMIN_USER
    IdentityFile /home/$ADMIN_USER/.ssh/$(basename "$SSH_KEY")
    StrictHostKeyChecking accept-new
EOF
chmod 600 ~/.ssh/config"

echo "==> Copying backend/.env and adding cross-VM settings"
{
  cat "$ROOT_DIR/backend/.env"
  echo ""
  echo "CAPABILITIES_DOCKER_HOST=ssh://$ADMIN_USER@$CAP_PRIVATE_IP"
  echo "CAPABILITIES_HOST=$CAP_PRIVATE_IP"
} > /tmp/forge-remote.env
scp -i "$SSH_KEY" /tmp/forge-remote.env "$ADMIN_USER@$AGENTS_PUBLIC_IP:~/Forge-AI/backend/.env"
rm /tmp/forge-remote.env

echo "==> Installing the backend as a systemd service"
$SSH "sudo tee /etc/systemd/system/forge-backend.service > /dev/null <<'EOF'
[Unit]
Description=Forge AI backend
After=network.target docker.service

[Service]
Type=simple
User=$ADMIN_USER
WorkingDirectory=/home/$ADMIN_USER/Forge-AI/backend
EnvironmentFile=/home/$ADMIN_USER/Forge-AI/backend/.env
ExecStart=/home/$ADMIN_USER/Forge-AI/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload && sudo systemctl enable forge-backend && sudo systemctl restart forge-backend"

echo ""
echo "==> Done. Backend running at: http://$AGENTS_PUBLIC_IP:8000"
echo "    Point frontend/src/api.ts's BASE_URL at that address to use it from the local frontend."
echo "    Capabilities VM (management only, no public API): $CAP_PRIVATE_IP"
