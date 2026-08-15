#!/usr/bin/env bash

set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script with sudo." >&2
  exit 1
fi

bucket_name="${1:-}"
target_user="${2:-${SUDO_USER:-}}"
mount_root="/mnt/centagging-gcs"

if [[ -z "${bucket_name}" || -z "${target_user}" ]]; then
  echo "Usage: configure_gcs_mount.sh GCS_BUCKET [VM_USER]" >&2
  exit 1
fi

if [[ ! "${bucket_name}" =~ ^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$ ]]; then
  echo "Invalid Cloud Storage bucket name." >&2
  exit 1
fi

if ! command -v gcsfuse > /dev/null 2>&1; then
  echo "Cloud Storage FUSE is not installed." >&2
  exit 1
fi

if [[ "${target_user}" == "root" ]] || ! id "${target_user}" > /dev/null 2>&1; then
  echo "A non-root VM user is required: ${target_user}" >&2
  exit 1
fi

target_uid="$(id -u "${target_user}")"
target_gid="$(id -g "${target_user}")"

install -d -m 0755 "${mount_root}"

configured_bucket="$(awk -v mount_root="${mount_root}" \
  '$2 == mount_root && $3 == "gcsfuse" { print $1; exit }' \
  /etc/fstab)"

if mountpoint -q "${mount_root}"; then
  mounted_type="$(findmnt -n -o FSTYPE --target "${mount_root}")"
  if [[ "${mounted_type}" != "fuse.gcsfuse" && "${mounted_type}" != "gcsfuse" ]]; then
    echo "Another filesystem is already mounted at ${mount_root}." >&2
    exit 1
  fi

  if [[ "${configured_bucket}" != "${bucket_name}" ]]; then
    echo "Unmount ${mount_root} before changing its bucket configuration." >&2
    exit 1
  fi

  mounted_uid="$(findmnt -n -o OPTIONS --target "${mount_root}" \
    | tr ',' '\n' \
    | awk -F= '$1 == "user_id" { print $2; exit }')"
  if [[ "${mounted_uid}" != "${target_uid}" ]]; then
    umount "${mount_root}"
  fi
fi

fstab_tmp="$(mktemp /etc/fstab.centagging.XXXXXX)"
trap 'rm -f "${fstab_tmp}"' EXIT

awk -v mount_root="${mount_root}" \
  '$2 != mount_root { print }' \
  /etc/fstab > "${fstab_tmp}"

printf '%s %s gcsfuse rw,_netdev,allow_other,implicit_dirs,uid=%s,gid=%s 0 0\n' \
  "${bucket_name}" \
  "${mount_root}" \
  "${target_uid}" \
  "${target_gid}" \
  >> "${fstab_tmp}"

chown --reference=/etc/fstab "${fstab_tmp}"
chmod --reference=/etc/fstab "${fstab_tmp}"
mv "${fstab_tmp}" /etc/fstab
trap - EXIT
systemctl daemon-reload

if ! mountpoint -q "${mount_root}"; then
  mount "${mount_root}"
fi

mkdir -p \
  "${mount_root}/uploads" \
  "${mount_root}/sku-images"

write_test_path="${mount_root}/uploads/.mount-write-test-$$"
runuser -u "${target_user}" -- touch "${write_test_path}"
runuser -u "${target_user}" -- rm "${write_test_path}"

runuser -u "${target_user}" -- test -r "${mount_root}/uploads"
runuser -u "${target_user}" -- test -w "${mount_root}/uploads"
runuser -u "${target_user}" -- test -r "${mount_root}/sku-images"
runuser -u "${target_user}" -- test -w "${mount_root}/sku-images"

findmnt --target "${mount_root}"
echo "Cloud Storage bucket mount configuration is complete."
