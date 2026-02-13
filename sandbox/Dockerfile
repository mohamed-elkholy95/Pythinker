# ============================================================
# Stage 1: BUILDER — heavy installs, dev tools, Playwright
# ============================================================
FROM ubuntu:22.04 AS builder

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

RUN apt-get update && apt-get install -y x11vnc websockify xvfb \
    && rm -rf /var/lib/apt/lists/*

# Create user ubuntu (sudo removed in runtime stage)
RUN useradd -m -d /home/ubuntu -s /bin/bash ubuntu && \
    echo "ubuntu ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ubuntu

RUN mkdir -p /home/ubuntu/.vnc /run/user/1000 && chown -R ubuntu:ubuntu /home/ubuntu/.vnc /run/user/1000

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
    npm install -g pnpm@10.29.2 yarn@1.22.22

ENV PNPM_HOME=/home/ubuntu/.local/share/pnpm
ENV PATH=${PNPM_HOME}:${NVM_DIR}/versions/node/v${NODE_VERSION}/bin:$PATH

# GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | \
    gpg --dearmor -o /usr/share/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    > /etc/apt/sources.list.d/github-cli.list && \
    apt-get update && apt-get install -y gh && apt-get clean && rm -rf /var/lib/apt/lists/*

# Chrome for Testing (amd64)
ARG TARGETARCH
ENV CHROME_FOR_TESTING_PATH=/opt/chrome-for-testing
RUN mkdir -p ${CHROME_FOR_TESTING_PATH} && \
    if [ "$TARGETARCH" != "arm64" ]; then \
        apt-get update && apt-get install -y --no-install-recommends unzip && \
        CHROME_VER=128.0.6613.137 && \
        curl -fsSL "https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VER}/linux64/chrome-linux64.zip" \
            -o /tmp/chrome-linux64.zip && \
        unzip -q /tmp/chrome-linux64.zip -d /tmp/chrome-extract && \
        mv /tmp/chrome-extract/chrome-linux64/* ${CHROME_FOR_TESTING_PATH}/ && \
        chmod +x ${CHROME_FOR_TESTING_PATH}/chrome && rm -rf /tmp/chrome-linux64.zip /tmp/chrome-extract && \
        ln -sf ${CHROME_FOR_TESTING_PATH}/chrome /usr/local/bin/chrome-for-testing && \
        apt-get purge -y unzip && apt-get autoremove -y && apt-get clean && rm -rf /var/lib/apt/lists/*; \
    fi

RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# Fonts
RUN apt-get update && apt-get install -y fonts-noto-cjk fonts-noto-color-emoji locales \
    && locale-gen en_US.UTF-8 && apt-get clean && rm -rf /var/lib/apt/lists/*

# Dev tools (build stage only — not copied to runtime)
RUN apt-get update && apt-get install -y ripgrep jq git tree zip unzip ffmpeg imagemagick \
    x11-apps xdotool openbox x11-xserver-utils && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements.runtime.txt ./

RUN python3 -m pip install --no-cache-dir --upgrade pip wheel setuptools && \
    python3 -m pip install --no-cache-dir -r requirements.txt

ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers
RUN python3 -m pip install --no-cache-dir playwright playwright-stealth && \
    python3 -m playwright install --with-deps chromium firefox webkit && \
    chown -R ubuntu:ubuntu /opt/playwright-browsers 2>/dev/null || true

RUN if [ "$TARGETARCH" = "arm64" ]; then \
    PW_CHROME=$(find /opt/playwright-browsers -name chrome -path '*chrome-linux*' -type f 2>/dev/null | head -1) && \
    [ -n "$PW_CHROME" ] && ln -sf "$PW_CHROME" ${CHROME_FOR_TESTING_PATH}/chrome && ln -sf "$PW_CHROME" /usr/local/bin/chrome-for-testing || exit 1; \
    chown -R ubuntu:ubuntu ${CHROME_FOR_TESTING_PATH} /opt/playwright-browsers 2>/dev/null || true; \
    fi

# Python dev tools — BUILD ONLY (not in runtime)
RUN python3 -m pip install --no-cache-dir \
    black flake8 pylint mypy bandit pytest pytest-cov pytest-asyncio isort autopep8 cyclonedx-bom

# npm dev tools — BUILD ONLY (not in runtime)
RUN npm install -g prettier eslint typescript jest @types/node @cyclonedx/cyclonedx-npm

# pnpm globals: mcpb, mermaid-cli (no yarn per reference env)
RUN mkdir -p ${PNPM_HOME} /home/ubuntu/.config/pnpm /home/ubuntu/.local/share/pnpm/global/5 /home/ubuntu/.pnpm-store/v10/projects && \
    chown -R ubuntu:ubuntu ${PNPM_HOME} /home/ubuntu/.config /home/ubuntu/.local/share/pnpm /home/ubuntu/.pnpm-store && \
    su - ubuntu -c "export NVM_DIR=/usr/local/nvm; export PNPM_HOME=/home/ubuntu/.local/share/pnpm; export PNPM_STORE_PATH=/home/ubuntu/.pnpm-store; \
    . /usr/local/nvm/nvm.sh; export PATH=$PNPM_HOME:$NVM_DIR/versions/node/v${NODE_VERSION}/bin:$PATH; \
    pnpm config set store-dir /home/ubuntu/.pnpm-store; pnpm config set global-bin-dir $PNPM_HOME; pnpm config set ignore-scripts false; \
    pnpm add -g @anthropic-ai/mcpb@2.1.2 @mermaid-js/mermaid-cli@11.12.0"

# Base Python venv template
RUN python3 -m venv /opt/base-python-venv && \
    /opt/base-python-venv/bin/pip install --no-cache-dir --upgrade pip wheel setuptools && \
    /opt/base-python-venv/bin/pip install --no-cache-dir -r /app/requirements.runtime.txt && \
    chown -R ubuntu:ubuntu /opt/base-python-venv

COPY . .
RUN touch /app/sandbox_context.json /app/sandbox_context.md && chown ubuntu:ubuntu /app/sandbox_context.json /app/sandbox_context.md

# Purge build-only apt packages
RUN apt-get update && apt-get purge -y --auto-remove software-properties-common \
    && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*


# ============================================================
# Stage 2: RUNTIME — production sandbox image
# ============================================================
FROM ubuntu:22.04 AS runtime

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV DEBIAN_FRONTEND=noninteractive
ENV HOSTNAME=sandbox

# Container init: tini for proper PID 1 (zombie reaping, signal forwarding)
# Core system + VNC + reference env packages
RUN apt-get update && apt-get install -y \
    tini \
    sudo bc curl wget gnupg ca-certificates socat supervisor \
    xterm perl xauth x11-xkb-utils xkb-data x11-utils dbus-x11 \
    libjpeg-turbo8 libpng16-16 libxfont2 libgl1-mesa-dri libgl1-mesa-glx libgif7 \
    libssl3 libgnutls30 libxtst6 libxrandr2 libxcursor1 libxinerama1 libxkbfile1 \
    x11vnc websockify xvfb openbox x11-xserver-utils x11-apps xdotool \
    poppler-utils graphviz \
    mysql-client lsof psmisc make patch vim nano xclip xdg-utils \
    ripgrep jq git tree zip unzip ffmpeg imagemagick \
    fonts-noto-cjk fonts-noto-color-emoji locales \
    && locale-gen en_US.UTF-8 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Playwright/Chromium runtime libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libdbus-1-3 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 \
    libpango-1.0-0 libcairo2 libxshmfence1 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Create ubuntu user — no NOPASSWD (removed for hardened non-root runtime)
RUN useradd -m -d /home/ubuntu -s /bin/bash ubuntu

RUN mkdir -p /home/ubuntu/.vnc /home/ubuntu/.config/openbox /run/user/1000 && \
    chown -R ubuntu:ubuntu /home/ubuntu /run/user/1000

# Copy from builder (no dev tools)
COPY --from=builder /opt/chrome-for-testing /opt/chrome-for-testing
COPY --from=builder /opt/base-python-venv /opt/base-python-venv
COPY --from=builder /opt/playwright-browsers /opt/playwright-browsers
COPY --from=builder /usr/local/nvm /usr/local/nvm
COPY --from=builder /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY --from=builder /usr/local/bin/python3.11 /usr/local/bin/python3.11
COPY --from=builder /home/ubuntu/.cache/ms-playwright /home/ubuntu/.cache/ms-playwright
COPY --from=builder /home/ubuntu/.local/share/pnpm /home/ubuntu/.local/share/pnpm

ENV NVM_DIR=/usr/local/nvm
ENV NODE_VERSION=22.13.0
ENV PNPM_HOME=/home/ubuntu/.local/share/pnpm
ENV PATH=${PNPM_HOME}:${NVM_DIR}/versions/node/v${NODE_VERSION}/bin:$PATH
ENV CHROME_FOR_TESTING_PATH=/opt/chrome-for-testing
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers

RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

WORKDIR /app
COPY --from=builder /app/app /app/app
COPY --from=builder /app/scripts /app/scripts
COPY --from=builder /app/openbox-rc.xml /app/openbox-rc.xml
COPY --from=builder /app/sandbox_context.json /app/sandbox_context.json
COPY --from=builder /app/sandbox_context.md /app/sandbox_context.md
COPY --from=builder /app/requirements.runtime.txt /app/requirements.runtime.txt
COPY --from=builder /app/requirements.txt /app/requirements.txt

RUN mkdir -p /home/ubuntu/.config/openbox && cp /app/openbox-rc.xml /home/ubuntu/.config/openbox/rc.xml && \
    chown -R ubuntu:ubuntu /home/ubuntu/.config

COPY supervisord.conf /etc/supervisor/conf.d/app.conf

ENV UVI_ARGS="" FRAMEWORK_UVI_ARGS="" CHROME_ARGS="" DISPLAY=:1
ENV CHROME_BIN="/opt/chrome-for-testing/chrome"

RUN chown -R ubuntu:ubuntu /home/ubuntu && chmod 750 /home/ubuntu && \
    mkdir -p /workspace && chown ubuntu:ubuntu /workspace && chmod 755 /workspace && \
    chown -R ubuntu:ubuntu /app

EXPOSE 8080 8082 9222 5900 5901

USER ubuntu
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["supervisord", "-n", "-c", "/app/supervisord.conf"]
