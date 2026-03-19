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
# Pinned to 0.7.12+ for patched jsonwebtoken Rust crate (CVE-2026-25537)
RUN curl -LsSf https://astral.sh/uv/0.7.12/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh

# Install Python dependencies (largest layer — cached unless requirements.txt changes)
COPY requirements.txt .
# Step 1: Upgrade pip/setuptools/wheel to patch bundled vulnerable versions
#   - pip>=25.1 fixes CVE-2026-1703, CVE-2025-8869
#   - setuptools>=78.1.0 vendors jaraco.context>=6.1.0 (CVE-2026-23949)
#   - wheel>=0.46.2 fixes permission traversal (CVE-2026-24049)
RUN uv pip install --system --no-cache "pip>=25.1" "setuptools>=78.1.0,<81" "wheel>=0.46.2" Cython && \
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

ARG GIT_VERSION=dev
ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown

LABEL org.opencontainers.image.title="pythinker-backend"
LABEL org.opencontainers.image.version=${GIT_VERSION}
LABEL org.opencontainers.image.revision=${GIT_SHA}
LABEL org.opencontainers.image.created=${BUILD_DATE}
LABEL org.opencontainers.image.source="https://github.com/mohamed-elkholy95/Pythinker"

ENV PYTHONUNBUFFERED=1
ENV GIT_VERSION=${GIT_VERSION}
ENV GIT_SHA=${GIT_SHA}
ENV BUILD_DATE=${BUILD_DATE}

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

# Non-root user for security (OWASP container hardening)
RUN addgroup --system --gid 1001 appuser && \
    adduser --system --uid 1001 --ingroup appuser appuser && \
    chown -R appuser:appuser /app
USER appuser

ENV PYTHONPATH=/app
ENV DSPY_CACHEDIR=/app/data/dspy_cache

EXPOSE 8000

CMD ["./run.sh"]
