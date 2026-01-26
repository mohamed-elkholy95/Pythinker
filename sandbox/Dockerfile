FROM ubuntu:22.04

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Avoid interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# Set hostname to sandbox
ENV HOSTNAME=sandbox

# Base system tools
RUN apt-get update && \
    apt-get install -y \
    sudo \
    bc \
    curl \
    wget \
    gnupg \
    ca-certificates \
    software-properties-common \
    xvfb \
    x11vnc \
    xterm \
    socat \
    supervisor \
    websockify \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create user ubuntu and grant sudo privileges
RUN useradd -m -d /home/ubuntu -s /bin/bash ubuntu && \
    echo "ubuntu ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ubuntu

# Install Python 3.11
RUN add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y python3.11 python3.11-venv python3.11-dev python3-pip && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 && \
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
    corepack enable && \
    corepack prepare pnpm@10.28.1 --activate && \
    corepack prepare yarn@1.22.22 --activate

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
RUN mkdir -p ${PNPM_HOME} && chown -R ubuntu:ubuntu ${PNPM_HOME} && \
    su - ubuntu -c "export NVM_DIR=/usr/local/nvm; source /usr/local/nvm/nvm.sh; corepack enable" && \
    su - ubuntu -c "export NVM_DIR=/usr/local/nvm; source /usr/local/nvm/nvm.sh; corepack prepare pnpm@10.28.1 --activate" && \
    su - ubuntu -c "export NVM_DIR=/usr/local/nvm; source /usr/local/nvm/nvm.sh; corepack prepare yarn@1.22.22 --activate" && \
    su - ubuntu -c "export NVM_DIR=/usr/local/nvm; source /usr/local/nvm/nvm.sh; pnpm add -g @anthropic-ai/mcpb@2.1.2 @mermaid-js/mermaid-cli@11.12.0 yarn@1.22.22 code-server@4.104.3"

# Create base Python virtual environment template for workspaces
RUN python3 -m venv /opt/base-python-venv && \
    /opt/base-python-venv/bin/pip install --no-cache-dir --upgrade pip wheel setuptools && \
    /opt/base-python-venv/bin/pip install --no-cache-dir -r /app/requirements.runtime.txt && \
    chown -R ubuntu:ubuntu /opt/base-python-venv

# Copy remaining project files
COPY . .

# Configure supervisor
COPY supervisord.conf /etc/supervisor/conf.d/app.conf

# Expose ports
EXPOSE 8080 9222 5900 5901

# Environment variables for service configuration
ENV UVI_ARGS=""
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
