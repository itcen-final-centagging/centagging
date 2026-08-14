#!/usr/bin/env bash

set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script with sudo." >&2
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
apt-get install -y ca-certificates curl

install -m 0755 -d /usr/share/keyrings
curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
  -o /usr/share/keyrings/cloud.google.asc
chmod a+r /usr/share/keyrings/cloud.google.asc

printf '%s\n' \
  "deb [signed-by=/usr/share/keyrings/cloud.google.asc] https://packages.cloud.google.com/apt cloud-sdk main" \
  > /etc/apt/sources.list.d/google-cloud-sdk.list

printf '%s\n' \
  "deb [signed-by=/usr/share/keyrings/cloud.google.asc] https://packages.cloud.google.com/apt gcsfuse-${ubuntu_codename} main" \
  > /etc/apt/sources.list.d/gcsfuse.list

apt-get update
apt-get install -y gcsfuse google-cloud-cli

gcloud version
gcsfuse --version

echo "Google Cloud CLI and Cloud Storage FUSE installation is complete."
