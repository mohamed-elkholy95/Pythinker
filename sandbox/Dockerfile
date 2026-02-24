# ============================================================
# Stage 1: BUILDER — heavy installs, dev tools, Playwright
# ============================================================
# USE_CHROMIUM=1: Prefer Playwright Chromium over Chrome for Testing.
FROM ubuntu:22.04 AS builder
ARG USE_CHROMIUM=0
ARG USE_CHROMIUM_APT=0
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

# Chrome for Testing (amd64) — skipped when USE_CHROMIUM=1 or USE_CHROMIUM_APT=1.
ARG TARGETARCH
ENV CHROME_FOR_TESTING_PATH=/opt/chrome-for-testing
RUN mkdir -p ${CHROME_FOR_TESTING_PATH} && \
    if [ "$USE_CHROMIUM" != "1" ] && [ "$USE_CHROMIUM_APT" != "1" ] && [ "$TARGETARCH" != "arm64" ]; then \
        apt-get update && apt-get install -y --no-install-recommends unzip && \
        CHROME_VER=131.0.6778.204 && \
        curl -fsSL "https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VER}/linux64/chrome-linux64.zip" \
            -o /tmp/chrome-linux64.zip && \
        unzip -q /tmp/chrome-linux64.zip -d /tmp/chrome-extract && \
        mv /tmp/chrome-extract/chrome-linux64/* ${CHROME_FOR_TESTING_PATH}/ && \
        chmod +x ${CHROME_FOR_TESTING_PATH}/chrome && rm -rf /tmp/chrome-linux64.zip /tmp/chrome-extract && \
        ln -sf ${CHROME_FOR_TESTING_PATH}/chrome /usr/local/bin/chrome-for-testing && \
        apt-get purge -y unzip && apt-get autoremove -y && apt-get clean && rm -rf /var/lib/apt/lists/*; \
    fi

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
RUN python3 -m venv /opt/base-python-venv && \
    /opt/base-python-venv/bin/pip install --no-cache-dir --upgrade pip wheel setuptools && \
    /opt/base-python-venv/bin/pip install --no-cache-dir -r /app/requirements.runtime.txt && \
    if [ "$ENABLE_SANDBOX_ADDONS" = "1" ]; then \
        /opt/base-python-venv/bin/pip install --no-cache-dir -r /app/requirements.addons.txt; \
    fi && \
    /opt/base-python-venv/bin/python -m playwright install --with-deps chromium firefox webkit && \
    (chown -R ubuntu:ubuntu /opt/base-python-venv /opt/playwright-browsers 2>/dev/null || true)

RUN if [ "$TARGETARCH" = "arm64" ] && [ "$USE_CHROMIUM" != "1" ]; then \
    PW_CHROME=$(find /opt/playwright-browsers -name chrome -path '*chrome-linux*' -type f 2>/dev/null | head -1) && \
    [ -n "$PW_CHROME" ] && ln -sf "$PW_CHROME" ${CHROME_FOR_TESTING_PATH}/chrome && ln -sf "$PW_CHROME" /usr/local/bin/chrome-for-testing || exit 1; \
    chown -R ubuntu:ubuntu ${CHROME_FOR_TESTING_PATH} /opt/playwright-browsers 2>/dev/null || true; \
    fi

# Node CLI tools used by sandbox code-dev/test endpoints
# yarn 1.22.22 matches the reference sandbox environment (report §3.1)
RUN npm install -g prettier eslint typescript jest @types/node yarn@1.22.22

# Optional pnpm globals (add-ons profile)
RUN mkdir -p ${PNPM_HOME} /home/ubuntu/.config/pnpm /home/ubuntu/.local/share/pnpm/global/5 /home/ubuntu/.pnpm-store/v10/projects && \
    chown -R ubuntu:ubuntu ${PNPM_HOME} /home/ubuntu/.config /home/ubuntu/.local/share/pnpm /home/ubuntu/.pnpm-store && \
    if [ "$ENABLE_SANDBOX_ADDONS" = "1" ]; then \
        su - ubuntu -c "export NVM_DIR=/usr/local/nvm; export PNPM_HOME=/home/ubuntu/.local/share/pnpm; export PNPM_STORE_PATH=/home/ubuntu/.pnpm-store; \
        . /usr/local/nvm/nvm.sh; export PATH=$PNPM_HOME:$NVM_DIR/versions/node/v${NODE_VERSION}/bin:$PATH; \
        pnpm config set store-dir /home/ubuntu/.pnpm-store; pnpm config set global-bin-dir $PNPM_HOME; pnpm config set ignore-scripts false; \
        pnpm add -g @anthropic-ai/mcpb@2.1.2 @mermaid-js/mermaid-cli@11.12.0"; \
    fi

COPY . .
RUN touch /app/sandbox_context.json /app/sandbox_context.md && chown ubuntu:ubuntu /app/sandbox_context.json /app/sandbox_context.md

# Purge build-only apt packages
RUN apt-get update && apt-get purge -y --auto-remove software-properties-common \
    && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*


# ============================================================
# Stage 2: RUNTIME — production sandbox image
# ============================================================
ARG USE_CHROMIUM=0
ARG USE_CHROMIUM_APT=0

FROM ubuntu:22.04 AS runtime
ARG USE_CHROMIUM=0
ARG USE_CHROMIUM_APT=0
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

# Playwright/Chromium runtime libs
# NOTE: Ubuntu 22.04 default chromium-browser is a snap stub (incompatible with Docker).
# USE_CHROMIUM=1 uses Playwright's bundled Chromium; USE_CHROMIUM_APT=1 installs the real
# deb from Rob Savoury's PPA (ppa:savoury1/chromium) at the pinned 128.0.6613.137 build
# that matches the reference sandbox environment exactly.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libdbus-1-3 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 \
    libpango-1.0-0 libcairo2 libxshmfence1 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# USE_CHROMIUM_APT=1: Install Chromium 128.0.6613.137 (Official Build, Ubuntu 22.04 64-bit)
# from Rob Savoury's PPA. Version is pinned and held to prevent unintended upgrades.
# PPA: https://launchpad.net/~savoury1/+archive/ubuntu/chromium
RUN if [ "$USE_CHROMIUM_APT" = "1" ]; then \
        apt-get update && apt-get install -y --no-install-recommends software-properties-common && \
        add-apt-repository -y ppa:savoury1/chromium && \
        apt-get update && \
        apt-get install -y --no-install-recommends \
            chromium-browser=1:128.0.6613.137-0ubuntu0.22.04.1sav0 \
            chromium-codecs-ffmpeg-extra=1:128.0.6613.137-0ubuntu0.22.04.1sav0 && \
        apt-mark hold chromium-browser chromium-codecs-ffmpeg-extra && \
        apt-get purge -y --auto-remove software-properties-common && \
        apt-get clean && rm -rf /var/lib/apt/lists/* && \
        mkdir -p /opt/chrome-for-testing && \
        ln -sf /usr/bin/chromium-browser /opt/chrome-for-testing/chrome && \
        ln -sf /usr/bin/chromium-browser /usr/local/bin/chromium && \
        echo "USE_CHROMIUM_APT=1: Chromium 128.0.6613.137 installed from ppa:savoury1/chromium"; \
    fi

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

# code-server 4.104.3 — VS Code in the browser (matches reference sandbox §5)
# Installed when ENABLE_SANDBOX_ADDONS=1; placed at /usr/local/bin/code-server.
RUN if [ "$ENABLE_SANDBOX_ADDONS" = "1" ]; then \
        ARCH=$(dpkg --print-architecture) && \
        curl -fOL "https://github.com/coder/code-server/releases/download/v4.104.3/code-server_4.104.3_${ARCH}.deb" \
            -o /tmp/code-server.deb && \
        dpkg -i /tmp/code-server.deb && \
        rm /tmp/code-server.deb && \
        echo "code-server 4.104.3 installed"; \
    fi

# Copy from builder (no dev tools); chrome-for-testing empty when USE_CHROMIUM=1
COPY --from=builder /opt/chrome-for-testing /opt/chrome-for-testing
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
ENV CHROME_FOR_TESTING_PATH=/opt/chrome-for-testing
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers

RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# When USE_CHROMIUM=1 (and not USE_CHROMIUM_APT): symlink Playwright Chromium to common paths.
# USE_CHROMIUM_APT takes precedence — it already placed the symlink above.
RUN if [ "$USE_CHROMIUM" = "1" ] && [ "$USE_CHROMIUM_APT" != "1" ]; then \
        PW_CHROMIUM=$(find /opt/playwright-browsers -name chrome -path '*/chromium-*/chrome-linux*/chrome' -type f 2>/dev/null | head -1); \
        if [ -n "$PW_CHROMIUM" ]; then \
            mkdir -p /usr/local/bin && \
            ln -sf "$PW_CHROMIUM" /usr/local/bin/chromium && \
            ln -sf "$PW_CHROMIUM" /usr/bin/chromium-browser && \
            echo "Symlinked Playwright Chromium: $PW_CHROMIUM -> /usr/local/bin/chromium,/usr/bin/chromium-browser"; \
        else \
            echo "WARNING: Playwright Chromium not found in /opt/playwright-browsers"; \
            find /opt/playwright-browsers -type f -name chrome 2>/dev/null || echo "No chrome binaries found"; \
        fi; \
    fi

WORKDIR /app
COPY --from=builder /app/app /app/app
COPY --from=builder /app/scripts /app/scripts
COPY --from=builder /app/sandbox_context.json /app/sandbox_context.json
COPY --from=builder /app/sandbox_context.md /app/sandbox_context.md
COPY --from=builder /app/requirements.runtime.txt /app/requirements.runtime.txt
COPY --from=builder /app/requirements.addons.txt /app/requirements.addons.txt
COPY --from=builder /app/requirements.txt /app/requirements.txt

COPY supervisord.conf /app/supervisord.conf

ENV UVI_ARGS="" FRAMEWORK_UVI_ARGS="" CHROME_ARGS="" SANDBOX_STREAMING_MODE=cdp_only

# BROWSER_PATH: When USE_CHROMIUM=1, symlink Playwright Chromium to the default path
# so BROWSER_PATH=/opt/chrome-for-testing/chrome works for both modes.
# This is the cleanest approach since Docker ENV can't be conditional.
RUN if [ "$USE_CHROMIUM" = "1" ] && [ "$USE_CHROMIUM_APT" != "1" ] && [ -f /usr/local/bin/chromium ]; then \
        mkdir -p /opt/chrome-for-testing && \
        ln -sf /usr/local/bin/chromium /opt/chrome-for-testing/chrome && \
        echo "USE_CHROMIUM=1: symlinked /usr/local/bin/chromium -> /opt/chrome-for-testing/chrome"; \
    fi

ENV BROWSER_PATH=/opt/chrome-for-testing/chrome
ENV CHROME_BIN="/opt/chrome-for-testing/chrome"

RUN chown -R ubuntu:ubuntu /home/ubuntu && chmod 750 /home/ubuntu && \
    mkdir -p /workspace && chown ubuntu:ubuntu /workspace && chmod 755 /workspace && \
    chown -R ubuntu:ubuntu /app

EXPOSE 8080 8082 9222 8443

# Health check: verify sandbox API is responding
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -sf http://localhost:8080/health || exit 1

USER ubuntu
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["supervisord", "-n", "-c", "/app/supervisord.conf"]
