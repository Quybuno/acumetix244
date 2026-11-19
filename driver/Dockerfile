# Deep Review Acunetix Scanner Driver
# Base image: Python 3.12 Alpine (minimal, lightweight)
FROM python:3.12-alpine

# Security: Create non-root user and group with UID/GID 1000
RUN addgroup -g 1000 driver && \
    adduser -u 1000 -G driver -s /bin/sh -D driver

# Set working directory
WORKDIR /app

# Copy driver source code
COPY driver/ /app/driver/

# Set ownership to non-root user
RUN chown -R driver:driver /app

# Switch to non-root user
USER driver

# Set python path
ENV PYTHONPATH=/app

# Default entrypoint runs driver CLI
ENTRYPOINT ["python3", "-m", "driver.main"]
CMD ["--help"]
