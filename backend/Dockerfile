FROM python:3.12-slim

WORKDIR /app

# Install curl
RUN apt-get update && apt-get install -y curl

# Install uv
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs

# Install uv
RUN pip install uv

# Configure uv to use Aliyun mirror
ENV UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

# Install dependencies
COPY requirements.txt .
RUN apt-get update && apt-get install -y gcc g++ python3-dev \
    libxcb1 libxcb-util1 libxrender1 libxext6 libglib2.0-0 \
    libgl1 libgles2 libglx0 libegl1 \
    && rm -rf /var/lib/apt/lists/* && \
    python -m pip install "setuptools<81" Cython && \
    python -m pip install --no-build-isolation --no-cache-dir editdistpy==0.1.6 && \
    uv pip install --system --no-cache -r requirements.txt

# Copy project files
COPY . .

# Set script execution permissions
RUN chmod +x run.sh

# Create persistent DSPy/LiteLLM disk cache directory.
# Mounted as a named volume in docker-compose so LLM call results
# survive container restarts and avoid re-spending tokens on re-evaluation.
RUN mkdir -p /app/data/dspy_cache

# Set environment variables
ENV PYTHONPATH=/app
# DSPy/LiteLLM will read this env var to locate the disk cache.
# Override with DSPY_CACHE_DIR in docker-compose if you want a different path.
ENV DSPY_CACHEDIR=/app/data/dspy_cache

# Expose port
EXPOSE 8000

# Start command
CMD ["./run.sh"] 