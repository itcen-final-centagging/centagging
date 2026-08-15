#!/usr/bin/env bash

set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script with sudo." >&2
  exit 1
fi

target_user="${1:-${SUDO_USER:-}}"

if [[ -z "${target_user}" || "${target_user}" == "root" ]]; then
  echo "A non-root VM administrator user is required." >&2
  exit 1
fi

if ! id "${target_user}" > /dev/null 2>&1; then
  echo "VM administrator user does not exist: ${target_user}" >&2
  exit 1
fi

# shellcheck disable=SC1091
source /etc/os-release

if [[ "${ID:-}" != "ubuntu" ]]; then
  echo "This script supports Ubuntu only." >&2
  exit 1
fi

ubuntu_codename="${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}"

if [[ -z "${ubuntu_codename}" ]]; then
  echo "Unable to determine the Ubuntu codename." >&2
  exit 1
fi

apt-get update
apt-get install -y ca-certificates curl git rsync

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

architecture="$(dpkg --print-architecture)"
printf '%s\n' \
  "deb [arch=${architecture} signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${ubuntu_codename} stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update
apt-get install -y \
  containerd.io \
  docker-buildx-plugin \
  docker-ce \
  docker-ce-cli \
  docker-compose-plugin

systemctl enable --now docker
usermod -aG docker "${target_user}"

target_group="$(id -gn "${target_user}")"
install -d -m 0755 \
  -o "${target_user}" \
  -g "${target_group}" \
  /opt/centagging

docker version --format 'Docker Engine {{.Server.Version}}'
docker compose version

echo "VM container runtime setup is complete."
echo "Reconnect the SSH session before running Docker as ${target_user}."
