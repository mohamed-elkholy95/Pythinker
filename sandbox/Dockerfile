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

# Node.js 22.13.0 via NVM
ENV NVM_DIR=/usr/local/nvm
ENV NODE_VERSION=22.13.0
RUN mkdir -p ${NVM_DIR} && \
    curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash && \
    . ${NVM_DIR}/nvm.sh && nvm install ${NODE_VERSION} && nvm alias default ${NODE_VERSION} && nvm use default && \
    npm install -g pnpm@10.29.2

ENV PNPM_HOME=/home/ubuntu/.local/share/pnpm
ENV PATH=${PNPM_HOME}:${NVM_DIR}/versions/node/v${NODE_VERSION}/bin:$PATH

RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# uv — fast Python package/project manager (matches reference sandbox §3.1)
# Installed as a standalone binary so agents can use it without activating a venv.
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh

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
RUN python3 -m venv /opt/base-python-venv && \
    uv pip install --python /opt/base-python-venv/bin/python --no-cache -r /app/requirements.runtime.txt && \
    if [ "$ENABLE_SANDBOX_ADDONS" = "1" ]; then \
        uv pip install --python /opt/base-python-venv/bin/python --no-cache -r /app/requirements.addons.txt; \
    fi && \
    /opt/base-python-venv/bin/python -m playwright install --with-deps chromium && \
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

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV DEBIAN_FRONTEND=noninteractive
ENV HOSTNAME=sandbox

# Container init: tini for proper PID 1 (zombie reaping, signal forwarding)
# Minimal core profile: only packages required by sandbox services.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tini \
    sudo bc curl wget gnupg ca-certificates socat supervisor \
    xterm perl xauth x11-xkb-utils xkb-data x11-utils dbus-x11 \
    libjpeg-turbo8 libpng16-16 libxfont2 libgl1-mesa-dri libgl1-mesa-glx libgif7 \
    libssl3 libgnutls30 libxtst6 libxrandr2 libxcursor1 libxinerama1 libxkbfile1 \
    ripgrep jq git zip unzip \
    xvfb openbox x11vnc python3-websockify \
    poppler-utils \
    fonts-noto-cjk fonts-noto-color-emoji \
    fonts-liberation fonts-dejavu-core fonts-freefont-ttf fontconfig \
    locales && \
    if [ "$ENABLE_SANDBOX_ADDONS" = "1" ]; then \
        apt-get install -y --no-install-recommends \
            graphviz mysql-client lsof psmisc make patch \
            vim nano xclip xdg-utils tree ffmpeg imagemagick xdotool x11-apps; \
    fi && \
    locale-gen en_US.UTF-8 && \
    fc-cache -f && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Playwright Chromium runtime libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libdbus-1-3 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 \
    libpango-1.0-0 libcairo2 libxshmfence1 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Create ubuntu user — no NOPASSWD (removed for hardened non-root runtime)
RUN useradd -m -d /home/ubuntu -s /bin/bash ubuntu

RUN mkdir -p /run/user/1000 && \
    chown -R ubuntu:ubuntu /home/ubuntu /run/user/1000

# gh CLI — GitHub CLI for repository operations (matches reference sandbox §3.2)
# Uses official GitHub apt repository for a proper signed installation.
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg && \
    chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list && \
    apt-get update && apt-get install -y --no-install-recommends gh && \
    apt-get clean && rm -rf /var/lib/apt/lists/*


# Copy from builder
COPY --from=builder /opt/base-python-venv /opt/base-python-venv
COPY --from=builder /opt/playwright-browsers /opt/playwright-browsers
COPY --from=builder /usr/local/nvm /usr/local/nvm
COPY --from=builder /usr/lib/python3.11 /usr/lib/python3.11
COPY --from=builder /usr/bin/python3.11 /usr/bin/python3.11
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv
COPY --from=builder /home/ubuntu/.local/share/pnpm /home/ubuntu/.local/share/pnpm

ENV NVM_DIR=/usr/local/nvm
ENV NODE_VERSION=22.13.0
ENV PNPM_HOME=/home/ubuntu/.local/share/pnpm
ENV VIRTUAL_ENV=/opt/base-python-venv
ENV SANDBOX_ADDONS_ENABLED=${ENABLE_SANDBOX_ADDONS}
ENV PATH=${VIRTUAL_ENV}/bin:${PNPM_HOME}:${NVM_DIR}/versions/node/v${NODE_VERSION}/bin:$PATH
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers
ENV PYTHONIOENCODING=utf-8
ENV LANG=C.UTF-8
ENV PW_TEST_SCREENSHOT_NO_FONTS_READY=1

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
    SUPERVISOR_RPC_USERNAME=supervisor \
    SUPERVISOR_RPC_PASSWORD=supervisor-dev-password

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
