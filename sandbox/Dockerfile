FROM ubuntu:22.04

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Avoid interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# Set hostname to sandbox
ENV HOSTNAME=sandbox

# Base system tools (VNC provided by x11vnc + websockify, installed separately)
RUN apt-get update && \
    apt-get install -y \
    sudo \
    bc \
    curl \
    wget \
    gnupg \
    ca-certificates \
    software-properties-common \
    python3-apt \
    xterm \
    socat \
    supervisor \
    libjpeg-turbo8 \
    libpng16-16 \
    libxfont2 \
    libgl1-mesa-dri \
    libgl1-mesa-glx \
    libgif7 \
    libssl3 \
    libgnutls30 \
    libxtst6 \
    libxrandr2 \
    libxcursor1 \
    libxinerama1 \
    libxkbfile1 \
    perl \
    xauth \
    x11-xkb-utils \
    xkb-data \
    x11-utils \
    dbus-x11 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install x11vnc + websockify (lightweight VNC stack)
RUN apt-get update && apt-get install -y \
    x11vnc \
    websockify \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# Create user ubuntu and grant sudo privileges
RUN useradd -m -d /home/ubuntu -s /bin/bash ubuntu && \
    echo "ubuntu ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ubuntu

# Configure VNC directories for ubuntu user
RUN mkdir -p /home/ubuntu/.vnc /run/user/1000 && \
    chown -R ubuntu:ubuntu /home/ubuntu/.vnc /run/user/1000

# Install Python 3.11
RUN add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y python3.11 python3.11-venv python3.11-dev python3-pip && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Node.js 22.13.0 via NVM
ENV NVM_DIR=/usr/local/nvm
ENV NODE_VERSION=22.13.0
RUN mkdir -p ${NVM_DIR} && \
    curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash && \
    source ${NVM_DIR}/nvm.sh && \
    nvm install ${NODE_VERSION} && \
    nvm alias default ${NODE_VERSION} && \
    nvm use default && \
    npm install -g pnpm@10.28.1 yarn@1.22.22

ENV PNPM_HOME=/home/ubuntu/.local/share/pnpm
ENV PATH=${PNPM_HOME}:${NVM_DIR}/versions/node/v${NODE_VERSION}/bin:$PATH

# Install GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | \
        gpg --dearmor -o /usr/share/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list && \
    apt-get update && \
    apt-get install -y gh && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Chromium
RUN add-apt-repository ppa:xtradeb/apps -y && \
    apt-get update && \
    apt-get install -y chromium --no-install-recommends && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Switch python3 to Python 3.11 after add-apt-repository usage
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# Install fonts and language support
RUN apt-get update && apt-get install -y \
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    language-pack-zh-hans \
    locales \
    && locale-gen zh_CN.UTF-8 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install additional development tools
RUN apt-get update && apt-get install -y \
    ripgrep \
    jq \
    git \
    tree \
    zip \
    unzip \
    ffmpeg \
    imagemagick \
    x11-apps \
    xdotool \
    openbox \
    x11-xserver-utils \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency files first to leverage cache
COPY requirements.txt requirements.runtime.txt ./

# Install Python dependencies for sandbox service
RUN python3 -m pip install --no-cache-dir --upgrade pip wheel setuptools && \
    python3 -m pip install --no-cache-dir -r requirements.txt

# Install Playwright and browsers for advanced browser automation
RUN python3 -m pip install --no-cache-dir playwright playwright-stealth && \
    python3 -m playwright install --with-deps chromium firefox webkit

# Install Python development tools (formatters, linters, testing)
RUN python3 -m pip install --no-cache-dir \
    black \
    flake8 \
    pylint \
    mypy \
    bandit \
    pytest \
    pytest-cov \
    pytest-asyncio \
    isort \
    autopep8 \
    cyclonedx-bom

# Install JavaScript/TypeScript development tools
RUN npm install -g \
    prettier \
    eslint \
    typescript \
    jest \
    @types/node \
    @cyclonedx/cyclonedx-npm

# Install global pnpm tools under ubuntu user
RUN mkdir -p ${PNPM_HOME} /home/ubuntu/.config/pnpm /home/ubuntu/.local/share/pnpm/global/5 /home/ubuntu/.pnpm-store/v10/projects && \
    chown -R ubuntu:ubuntu ${PNPM_HOME} /home/ubuntu/.config /home/ubuntu/.local/share/pnpm /home/ubuntu/.pnpm-store && \
    su - ubuntu -c "export NVM_DIR=/usr/local/nvm; export PNPM_HOME=/home/ubuntu/.local/share/pnpm; export PNPM_STORE_PATH=/home/ubuntu/.pnpm-store; source /usr/local/nvm/nvm.sh; export PATH=$PNPM_HOME:$NVM_DIR/versions/node/v${NODE_VERSION}/bin:$PATH; pnpm config set store-dir /home/ubuntu/.pnpm-store; pnpm config set global-bin-dir $PNPM_HOME; pnpm config set ignore-scripts false; pnpm add -g @anthropic-ai/mcpb@2.1.2 @mermaid-js/mermaid-cli@11.12.0 yarn@1.22.22"

# Create base Python virtual environment template for workspaces
RUN python3 -m venv /opt/base-python-venv && \
    /opt/base-python-venv/bin/pip install --no-cache-dir --upgrade pip wheel setuptools && \
    /opt/base-python-venv/bin/pip install --no-cache-dir -r /app/requirements.runtime.txt && \
    chown -R ubuntu:ubuntu /opt/base-python-venv

# Copy remaining project files
COPY . .

# Ensure sandbox context output files are writable by ubuntu user
RUN touch /app/sandbox_context.json /app/sandbox_context.md && \
    chown ubuntu:ubuntu /app/sandbox_context.json /app/sandbox_context.md

# Configure supervisor
COPY supervisord.conf /etc/supervisor/conf.d/app.conf

# Configure openbox window manager
RUN mkdir -p /home/ubuntu/.config/openbox
COPY openbox-rc.xml /home/ubuntu/.config/openbox/rc.xml
RUN chown -R ubuntu:ubuntu /home/ubuntu/.config

# Expose ports
# 8080: Main sandbox API
# 8082: Framework API
# 9222: Chrome DevTools
# 5900: VNC native protocol
# 5901: WebSocket VNC (websockify)
EXPOSE 8080 8082 9222 5900 5901

# Environment variables for service configuration
ENV UVI_ARGS=""
ENV FRAMEWORK_UVI_ARGS=""
ENV CHROME_ARGS=""
ENV DISPLAY=:1

# Security: Remove unnecessary development packages and clean up
RUN apt-get update && apt-get purge -y --auto-remove \
    software-properties-common \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Security: Ensure ubuntu user owns home directory and restrict permissions
RUN chown -R ubuntu:ubuntu /home/ubuntu && \
    chmod 750 /home/ubuntu

# Security: Create workspace directory for user code execution
RUN mkdir -p /workspace && chown ubuntu:ubuntu /workspace && chmod 755 /workspace

# Use supervisor to start all services
CMD ["supervisord", "-n", "-c", "/app/supervisord.conf"]
