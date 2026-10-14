FROM python:3.12-slim

# Prevent Python from writing .pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install system dependencies required for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install compatible, explicitly pinned CPU-only PyTorch from the official PyTorch CPU wheel distribution
RUN pip install --no-cache-dir --default-timeout=30 --retries=1 \
    torch==2.14.1+cpu \
    --index-url https://download.pytorch.org/whl/cpu \
    || pip install --no-cache-dir \
    "https://d21usjoq99fcb9.cloudfront.net/whl/cpu/torch-2.14.1%2Bcpu-cp312-cp312-manylinux_2_28_x86_64.whl"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=1000 --retries=10 -r requirements.txt

# Configure environment variables for non-root user and model caches
ENV HOME=/home/appuser \
    HF_HOME=/home/appuser/.cache/huggingface \
    TORCH_HOME=/home/appuser/.cache/torch

# Create dedicated non-root application user and group
RUN groupadd --system --gid 10001 appgroup && \
    useradd --system --uid 10001 --gid appgroup --create-home --home-dir /home/appuser --shell /bin/bash appuser

# Copy backend application source code
COPY --chown=appuser:appgroup . .

# Set up writable model cache directories with minimum required permissions
RUN mkdir -p /home/appuser/.cache/huggingface /home/appuser/.cache/torch && \
    chown -R appuser:appgroup /app /home/appuser

# Switch to non-root application user
USER appuser

# Expose FastAPI default port
EXPOSE 8000

# Run uvicorn server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
