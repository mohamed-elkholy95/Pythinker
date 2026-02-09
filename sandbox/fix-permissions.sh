#!/bin/bash
# Prepare writable runtime/cache dirs for the unprivileged sandbox user.

set -e

# Best-effort temp dir permissions.
if [ -d "/tmp" ]; then
    chmod 1777 /tmp 2>/dev/null || true
fi

# Stable runtime dir for Chromium/Openbox in restricted containers.
mkdir -p /tmp/runtime-ubuntu
chown ubuntu:ubuntu /tmp/runtime-ubuntu 2>/dev/null || true
chmod 700 /tmp/runtime-ubuntu 2>/dev/null || true

# Keep /run/user/1000 usable when present.
if [ -d "/run/user/1000" ]; then
    chown -R ubuntu:ubuntu /run/user/1000 2>/dev/null || true
    chmod 700 /run/user/1000 2>/dev/null || true
fi

# Ensure cache/config locations exist for the ubuntu user. In hardened
# containers root may not have DAC override, so run setup as ubuntu as well.
chown -R ubuntu:ubuntu /home/ubuntu/.cache 2>/dev/null || true
su -s /bin/sh ubuntu -c "mkdir -p /home/ubuntu/.cache /home/ubuntu/.cache/openbox /home/ubuntu/.config"
su -s /bin/sh ubuntu -c "chmod 700 /home/ubuntu/.cache /home/ubuntu/.cache/openbox"
su -s /bin/sh ubuntu -c "mkdir -p /tmp/runtime-ubuntu/dconf && chmod 700 /tmp/runtime-ubuntu /tmp/runtime-ubuntu/dconf"

echo "Permissions prepared for sandbox runtime"
