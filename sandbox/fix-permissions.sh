#!/bin/bash
# Fix tmpfs mount permissions for ubuntu user
# This script runs at container startup to fix ownership of tmpfs mounts

set -e

# Fix cache directory (mounted as tmpfs with root ownership)
if [ -d "/home/ubuntu/.cache" ]; then
    chown -R ubuntu:ubuntu /home/ubuntu/.cache
    chmod 755 /home/ubuntu/.cache
fi

# Fix tmp directory if needed
if [ -d "/tmp" ]; then
    chmod 1777 /tmp
fi

# Fix run/user directory
if [ -d "/run/user/1000" ]; then
    chown -R ubuntu:ubuntu /run/user/1000
    chmod 700 /run/user/1000
fi

echo "Permissions fixed for tmpfs mounts"
