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

# Create /run/user/1000 for Xvfb and x11vnc runtime dir.
# The tmpfs mount on /run wipes the directory created during docker build,
# so we must recreate it here at container startup.
mkdir -p /run/user/1000
chown ubuntu:ubuntu /run/user/1000
chmod 700 /run/user/1000

# Ensure cache/config locations exist for the ubuntu user. In hardened
# containers root may not have DAC override, so run setup as ubuntu as well.
chown -R ubuntu:ubuntu /home/ubuntu/.cache 2>/dev/null || true
su -s /bin/sh ubuntu -c "mkdir -p /home/ubuntu/.cache /home/ubuntu/.cache/openbox /home/ubuntu/.config"
su -s /bin/sh ubuntu -c "chmod 700 /home/ubuntu/.cache /home/ubuntu/.cache/openbox"
su -s /bin/sh ubuntu -c "mkdir -p /tmp/runtime-ubuntu/dconf && chmod 700 /tmp/runtime-ubuntu /tmp/runtime-ubuntu/dconf"

echo "Permissions prepared for sandbox runtime"
