# ============================================================
# Stage 1: BUILDER — heavy installs, dev tools, Playwright
# ============================================================
FROM ubuntu:22.04 AS builder
ARG ENABLE_SANDBOX_ADDONS=0

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV DEBIAN_FRONTEND=noninteractive
ENV HOSTNAME=sandbox

# Base system tools
RUN apt-get update && apt-get install -y \
    sudo bc curl wget gnupg ca-certificates software-properties-common python3-apt \
    xterm socat supervisor libjpeg-turbo8 libpng16-16 libxfont2 libgl1-mesa-dri \
    libgl1-mesa-glx libgif7 libssl3 libgnutls30 libxtst6 libxrandr2 libxcursor1 \
    libxinerama1 libxkbfile1 perl xauth x11-xkb-utils xkb-data x11-utils dbus-x11 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Create user ubuntu (sudo removed in runtime stage)
RUN useradd -m -d /home/ubuntu -s /bin/bash ubuntu && \
    echo "ubuntu ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ubuntu

RUN mkdir -p /run/user/1000 && chown -R ubuntu:ubuntu /run/user/1000

# Python 3.11
RUN add-apt-repository ppa:deadsnakes/ppa && apt-get update && \
    apt-get install -y python3.11 python3.11-venv python3.11-dev python3-pip && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Node.js 22 LTS via NVM
ENV NVM_DIR=/usr/local/nvm
ENV NODE_VERSION=22.22.1
RUN mkdir -p ${NVM_DIR} && \
    curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash && \
    . ${NVM_DIR}/nvm.sh && nvm install ${NODE_VERSION} && nvm alias default ${NODE_VERSION} && nvm use default && \
    npm install -g npm@latest && \
    npm install -g pnpm@latest
# npm@latest pulls tar>=7.5.11, minimatch>=10.2.3, glob>=11.1.0 (fixes 22 Trivy HIGH alerts)

ENV PNPM_HOME=/home/ubuntu/.local/share/pnpm
ENV PATH=${PNPM_HOME}:${NVM_DIR}/versions/node/v${NODE_VERSION}/bin:$PATH

RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# uv — fast Python package/project manager (matches reference sandbox §3.1)
# Pinned to 0.7.x to get patched jsonwebtoken Rust crate (fixes CVE alerts #211, #212)
RUN curl -LsSf https://astral.sh/uv/0.7.12/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh

# Fonts — comprehensive set for proper web rendering
# fonts-liberation: metric-compatible with Arial, Times New Roman, Courier (used by 90%+ of websites)
# fonts-dejavu-core: fallback sans/serif/mono
# fonts-freefont-ttf: additional Unicode coverage
# fontconfig: font configuration and caching system
RUN apt-get update && apt-get install -y \
    fonts-noto-cjk fonts-noto-color-emoji \
    fonts-liberation fonts-dejavu-core fonts-freefont-ttf fontconfig \
    locales \
    && locale-gen en_US.UTF-8 \
    && fc-cache -f \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements.runtime.txt requirements.addons.txt ./

ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers
# Base Python venv template (used by sandbox API + per-workspace venv cloning)
# Uses uv for ~10-20x faster installs vs pip
# Step 1: Upgrade pip/setuptools/wheel FIRST to replace system-bundled vulnerable versions
#   - setuptools>=78.1.0 vendors jaraco.context>=6.1.0 (fixes CVE-2026-23949)
#   - wheel>=0.46.2 fixes permission traversal (CVE-2026-24049)
RUN python3 -m venv /opt/base-python-venv && \
    uv pip install --python /opt/base-python-venv/bin/python --no-cache \
        "pip>=25.1" "setuptools>=78.1.0" "wheel>=0.46.2" && \
    uv pip install --python /opt/base-python-venv/bin/python --no-cache -r /app/requirements.runtime.txt && \
    if [ "$ENABLE_SANDBOX_ADDONS" = "1" ]; then \
        uv pip install --python /opt/base-python-venv/bin/python --no-cache -r /app/requirements.addons.txt; \
    fi && \
    /opt/base-python-venv/bin/python -m playwright install --with-deps chromium && \
    # Force-install standalone jaraco.context and wheel into the venv so Trivy sees the fixed versions
    uv pip install --python /opt/base-python-venv/bin/python --no-cache \
        "jaraco.context>=6.1.0" "wheel>=0.46.2" && \
    # Remove ensurepip bundled wheels (contain old pip/setuptools/wheel that Trivy flags)
    rm -rf /usr/lib/python3.11/ensurepip/_bundled/ && \
    # Remove ALL system-level dist-info that Trivy scans (covers both dist-packages paths)
    find /usr/lib/python3* -path '*/jaraco*context*' -exec rm -rf {} + 2>/dev/null; \
    find /usr/lib/python3* -path '*/wheel*' -name '*.dist-info' -exec rm -rf {} + 2>/dev/null; \
    rm -rf /usr/lib/python3/dist-packages/wheel* /usr/lib/python3/dist-packages/setuptools* \
           /usr/lib/python3/dist-packages/jaraco* /usr/lib/python3/dist-packages/pkg_resources* && \
    (chown -R ubuntu:ubuntu /opt/base-python-venv /opt/playwright-browsers 2>/dev/null || true)

# Node CLI tools used by sandbox code-dev/test endpoints
# yarn 1.22.22 matches the reference sandbox environment (report §3.1)
RUN npm install -g prettier eslint typescript jest @types/node yarn@1.22.22 @mermaid-js/mermaid-cli@11.12.0

# Optional pnpm globals (add-ons profile)
RUN mkdir -p ${PNPM_HOME} /home/ubuntu/.config/pnpm /home/ubuntu/.local/share/pnpm/global/5 /home/ubuntu/.pnpm-store/v10/projects && \
    chown -R ubuntu:ubuntu ${PNPM_HOME} /home/ubuntu/.config /home/ubuntu/.local/share/pnpm /home/ubuntu/.pnpm-store && \
    if [ "$ENABLE_SANDBOX_ADDONS" = "1" ]; then \
        su - ubuntu -c "export NVM_DIR=/usr/local/nvm; export PNPM_HOME=/home/ubuntu/.local/share/pnpm; export PNPM_STORE_PATH=/home/ubuntu/.pnpm-store; \
        . /usr/local/nvm/nvm.sh; export PATH=$PNPM_HOME:$NVM_DIR/versions/node/v${NODE_VERSION}/bin:$PATH; \
        pnpm config set store-dir /home/ubuntu/.pnpm-store; pnpm config set global-bin-dir $PNPM_HOME; pnpm config set ignore-scripts false; \
        pnpm add -g @anthropic-ai/mcpb@2.1.2"; \
    fi

# code-server — VS Code web IDE (addons profile only)
RUN if [ "$ENABLE_SANDBOX_ADDONS" = "1" ]; then \
        curl -fsSL https://code-server.dev/install.sh | sh && \
        code-server --install-extension ms-python.python 2>/dev/null || true && \
        code-server --install-extension dbaeumer.vscode-eslint 2>/dev/null || true; \
    fi

COPY . .
RUN touch /app/sandbox_context.json /app/sandbox_context.md && chown ubuntu:ubuntu /app/sandbox_context.json /app/sandbox_context.md

# Purge build-only apt packages
RUN apt-get update && apt-get purge -y --auto-remove software-properties-common \
    && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*


# ============================================================
# Stage 2: RUNTIME — production sandbox image
# ============================================================
FROM ubuntu:22.04 AS runtime
ARG ENABLE_SANDBOX_ADDONS=0
ARG GIT_VERSION=dev
ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown

LABEL org.opencontainers.image.title="pythinker-sandbox"
LABEL org.opencontainers.image.version=${GIT_VERSION}
LABEL org.opencontainers.image.revision=${GIT_SHA}
LABEL org.opencontainers.image.created=${BUILD_DATE}
LABEL org.opencontainers.image.source="https://github.com/mohamed-elkholy95/Pythinker"

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV DEBIAN_FRONTEND=noninteractive
ENV HOSTNAME=sandbox

# All runtime apt packages in a single layer to minimize image size.
# gh CLI installed separately below via .deb for version pinning (fixes CVE-2026-33186 in bundled grpc).
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Container init + core tools
    tini sudo bc curl wget gnupg ca-certificates socat supervisor \
    xterm perl xauth x11-xkb-utils xkb-data x11-utils x11-apps x11-xserver-utils xdotool dbus-x11 \
    # Cursor theme (replaces ugly default X11 cursor in screencast)
    dmz-cursor-theme \
    # Native libs for rendering
    libjpeg-turbo8 libpng16-16 libxfont2 libgl1-mesa-dri libgl1-mesa-glx libgif7 \
    libssl3 libgnutls30 libxtst6 libxrandr2 libxcursor1 libxinerama1 libxkbfile1 \
    # CLI tools (gh installed separately below for version pinning)
    ripgrep jq git zip unzip \
    # Display stack (Xvfb + VNC)
    xvfb openbox x11vnc python3-websockify \
    # PDF tools
    poppler-utils \
    # Playwright Chromium runtime libs
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libdbus-1-3 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 \
    libpango-1.0-0 libcairo2 libxshmfence1 \
    # Fonts
    fonts-noto-cjk fonts-noto-color-emoji \
    fonts-liberation fonts-dejavu-core fonts-freefont-ttf fontconfig \
    locales && \
    if [ "$ENABLE_SANDBOX_ADDONS" = "1" ]; then \
        apt-get install -y --no-install-recommends \
            graphviz mysql-client lsof psmisc make patch \
            vim nano xclip xdg-utils tree ffmpeg imagemagick; \
    fi && \
    locale-gen en_US.UTF-8 && \
    fc-cache -f && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# gh CLI — pinned version via official .deb (apt repo lags behind, bundled grpc had CVE-2026-33186)
ARG GH_VERSION=2.88.1
RUN curl -fsSL "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_$(dpkg --print-architecture).deb" \
        -o /tmp/gh.deb && \
    dpkg -i /tmp/gh.deb && rm -f /tmp/gh.deb

# Create ubuntu user — no NOPASSWD (removed for hardened non-root runtime)
RUN useradd -m -d /home/ubuntu -s /bin/bash ubuntu

RUN mkdir -p /run/user/1000 && \
    chown -R ubuntu:ubuntu /home/ubuntu /run/user/1000


# Copy from builder
COPY --from=builder --chown=ubuntu:ubuntu /opt/base-python-venv /opt/base-python-venv
COPY --from=builder /opt/playwright-browsers /opt/playwright-browsers
COPY --from=builder /usr/local/nvm /usr/local/nvm
COPY --from=builder /usr/lib/python3.11 /usr/lib/python3.11
COPY --from=builder /usr/bin/python3.11 /usr/bin/python3.11
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv
COPY --from=builder /home/ubuntu/.local/share/pnpm /home/ubuntu/.local/share/pnpm

ENV NVM_DIR=/usr/local/nvm
ENV NODE_VERSION=22.22.1
ENV PNPM_HOME=/home/ubuntu/.local/share/pnpm
ENV VIRTUAL_ENV=/opt/base-python-venv
ENV SANDBOX_ADDONS_ENABLED=${ENABLE_SANDBOX_ADDONS}
ENV PATH=${VIRTUAL_ENV}/bin:${PNPM_HOME}:${NVM_DIR}/versions/node/v${NODE_VERSION}/bin:$PATH
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers
ENV PYTHONIOENCODING=utf-8
ENV LANG=C.UTF-8
ENV PW_TEST_SCREENSHOT_NO_FONTS_READY=1
ENV GIT_VERSION=${GIT_VERSION}
ENV GIT_SHA=${GIT_SHA}
ENV BUILD_DATE=${BUILD_DATE}

RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# Symlink Playwright Chromium to standard paths for BROWSER_PATH and Mermaid CLI
RUN PW_CHROMIUM=$(find /opt/playwright-browsers -name chrome -path '*/chromium-*/chrome-linux*/chrome' -type f 2>/dev/null | head -1); \
    if [ -n "$PW_CHROMIUM" ]; then \
        mkdir -p /usr/local/bin && \
        ln -sf "$PW_CHROMIUM" /usr/local/bin/chromium && \
        ln -sf "$PW_CHROMIUM" /usr/bin/chromium-browser && \
        echo "Playwright Chromium: $PW_CHROMIUM -> /usr/local/bin/chromium, /usr/bin/chromium-browser"; \
    else \
        echo "ERROR: Playwright Chromium not found in /opt/playwright-browsers" && exit 1; \
    fi

# Mermaid CLI puppeteer config for containerized rendering (uses Playwright Chromium)
RUN echo '{"executablePath":"/usr/local/bin/chromium","args":["--no-sandbox","--disable-setuid-sandbox","--disable-gpu"],"timeout":60000}' > /opt/mermaid-puppeteer.json

WORKDIR /app
COPY --from=builder /app/app /app/app
COPY --from=builder /app/scripts /app/scripts
COPY --from=builder /app/sandbox_context.json /app/sandbox_context.json
COPY --from=builder /app/sandbox_context.md /app/sandbox_context.md
COPY --from=builder /app/requirements.runtime.txt /app/requirements.runtime.txt
COPY --from=builder /app/requirements.addons.txt /app/requirements.addons.txt
COPY --from=builder /app/requirements.txt /app/requirements.txt

# code-server (addons profile only — runtime install to avoid conditional COPY issues)
RUN if [ "$ENABLE_SANDBOX_ADDONS" = "1" ]; then \
        curl -fsSL https://code-server.dev/install.sh | sh; \
    fi

COPY supervisord.conf /app/supervisord.conf

ENV UVI_ARGS="" FRAMEWORK_UVI_ARGS="" CHROME_ARGS="" SANDBOX_STREAMING_MODE=cdp_only \
    SUPERVISOR_RPC_USERNAME=supervisor

ENV BROWSER_PATH=/usr/local/bin/chromium
ENV CHROME_BIN=/usr/local/bin/chromium

RUN chown -R ubuntu:ubuntu /home/ubuntu && chmod 750 /home/ubuntu && \
    mkdir -p /workspace && chown ubuntu:ubuntu /workspace && chmod 755 /workspace && \
    chown -R ubuntu:ubuntu /app

EXPOSE 8080 8082 9222 6080 8443

# Health check: verify sandbox API is responding
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -sf http://localhost:8080/health || exit 1

USER ubuntu
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["supervisord", "-n", "-c", "/app/supervisord.conf"]
