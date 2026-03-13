# ============================================================
# Stage 1: BUILDER — compile deps, install browsers
# ============================================================
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1
ENV UV_HTTP_TIMEOUT=300

WORKDIR /build

# Build tools + runtime libs needed by native wheels (lxml, Pillow, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ python3-dev curl \
    libxcb1 libxcb-util1 libxrender1 libxext6 libglib2.0-0 \
    libgl1 libgles2 libglx0 libegl1 \
    && rm -rf /var/lib/apt/lists/*

# Install uv (standalone binary — faster than pip install uv)
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh

# Install Python dependencies (largest layer — cached unless requirements.txt changes)
COPY requirements.txt .
RUN uv pip install --system --no-cache "setuptools<81" Cython && \
    uv pip install --system --no-cache --no-build-isolation editdistpy==0.1.6 && \
    uv pip install --system --no-cache -r requirements.txt

# Install Playwright Chromium for PDF rendering
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers
RUN playwright install --with-deps chromium

# Scrapling fetchers: browser/runtime assets for stealth scraping tiers
RUN scrapling install


# ============================================================
# Stage 2: RUNTIME — slim production image
# ============================================================
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Runtime-only system packages (no gcc/g++/dev tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    fonts-dejavu-core \
    fonts-liberation \
    # Playwright Chromium runtime dependencies
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libdbus-1-3 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libasound2 libpango-1.0-0 libcairo2 libxshmfence1 \
    # Shared libs for native Python wheels (Pillow, lxml, etc.)
    libxcb1 libxcb-util1 libxrender1 libxext6 libglib2.0-0 \
    libgl1 libgles2 libglx0 libegl1 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy Playwright browsers from builder
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers
COPY --from=builder /opt/playwright-browsers /opt/playwright-browsers

# Copy application code (.dockerignore excludes .venv, tests, docs, .git)
COPY . .

RUN chmod +x run.sh

# DSPy/LiteLLM disk cache (mounted as named volume in docker-compose)
RUN mkdir -p /app/data/dspy_cache

ENV PYTHONPATH=/app
ENV DSPY_CACHEDIR=/app/data/dspy_cache

EXPOSE 8000

CMD ["./run.sh"]
