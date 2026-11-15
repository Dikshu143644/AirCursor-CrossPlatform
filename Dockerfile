# ==============================================================================
# AirCursor Multi-Arch Dockerfile (linux/amd64, linux/arm64)
# Multi-stage lightweight container with Xvfb, x11vnc, noVNC, and AirCursor daemon
# ==============================================================================

# Stage 1: Builder & Asset Verification
FROM python:3.12-slim AS builder

WORKDIR /build

COPY pyproject.toml README.md ./
COPY aircursor_core/ ./aircursor_core/

# Verify pure Python core compilation
RUN python3 -m compileall aircursor_core/

# Stage 2: Production Runtime
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="AirCursor Cross-Platform" \
      org.opencontainers.image.description="AirPods Head-Tracking Cursor, Hands-Free Gesture Engine & Web Remote" \
      org.opencontainers.image.version="1.0.5" \
      org.opencontainers.image.licenses="MIT"

# Set environment defaults
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DISPLAY=:99 \
    SCREEN_WIDTH=1920 \
    SCREEN_HEIGHT=1080 \
    SCREEN_DEPTH=24 \
    HTTP_PORT=8765 \
    UDP_PORT=4242 \
    NOVNC_PORT=6080 \
    AUTORUN=true \
    MODE=synthetic \
    ENABLE_NOVNC=false

# Install Virtual Display Stack & Runtime Tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    x11vnc \
    novnc \
    websockify \
    curl \
    procps \
    net-tools \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged user and directories
RUN groupadd -g 1000 aircursor && \
    useradd -u 1000 -g aircursor -m -s /bin/bash aircursor && \
    mkdir -p /app /app/config /app/dist && \
    chown -R aircursor:aircursor /app /home/aircursor

WORKDIR /app

# Copy application artifacts
COPY --chown=aircursor:aircursor --from=builder /build/aircursor_core /app/aircursor_core
COPY --chown=aircursor:aircursor . /app/

# Install the optional local vision runtime (no cloud service required).
RUN python3 -m pip install --no-cache-dir '.[vision]'

# Ensure entrypoint is executable
RUN chmod +x /app/entrypoint.sh

# Expose Web Remote & API (8765), OpenTrack/AirPods UDP (4242/udp), and noVNC (6080)
EXPOSE 8765
EXPOSE 4242/udp

# Production Healthcheck targeting /status endpoint
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8765/status || exit 1

# Run unprivileged
USER aircursor

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python3", "server.py"]
