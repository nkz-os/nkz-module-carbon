# Multi-stage build for NKZ Carbon Module
# Stage 1: Dependencies
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies (git needed for nkz-platform-sdk from git)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy and install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Production image
FROM python:3.12-slim

WORKDIR /app

# Create non-root user
RUN groupadd -r carbon && useradd -r -g carbon carbon

# Copy installed packages from builder
COPY --from=builder /root/.local /home/carbon/.local

# Copy application code
COPY app/ ./app/

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/home/carbon/.local/bin:${PATH}"

# Switch to non-root user
USER carbon

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
