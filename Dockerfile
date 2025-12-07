# PailKit Dockerfile
# Builds the Flow service (which includes all API routes)
#
# Simple Explanation:
# This Dockerfile creates a container that runs the Flow service.
# All API routes (bot, rooms, transcribe) are now in flow/main.py.

# Use Python 3.12 as the base image
FROM python:3.12-slim

# Set the working directory inside the container
WORKDIR /app

# Set environment variables for Python
# PYTHONUNBUFFERED=1: Ensures Python output is sent directly to terminal (no buffering)
# PYTHONDONTWRITEBYTECODE=1: Prevents Python from creating .pyc files
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Copy requirements file first (for Docker layer caching)
# This allows Docker to cache the dependency installation step separately
# If requirements don't change, Docker will reuse the cached layer
COPY flow/requirements.txt /app/flow-requirements.txt

# Install Python dependencies
# --no-cache-dir: Don't store pip cache (reduces image size)
# --upgrade pip: Ensure we have the latest pip version
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/flow-requirements.txt

# Copy the rest of the application code
# Copy from project root to include flow/ module and shared/ common code
COPY shared /app/shared
COPY flow /app/flow

# Expose port 8080 (Fly.io will route traffic to this port)
EXPOSE 8080

# Keep working directory at /app (project root) so Python can find shared/ module
# Simple Explanation: When Python imports modules, it looks in the current directory
# and directories in PYTHONPATH. By staying at /app, Python can find:
# - flow/ (our main app with all routes)
# - shared/ (common code used by flow)
WORKDIR /app

# Run the FastAPI application using uvicorn
# Simple Explanation:
# - flow.main:app = "use the 'app' variable from the 'main.py' file in the 'flow' directory"
# - --host 0.0.0.0 = listen on all network interfaces (not just localhost)
# - --port ${PORT} = read PORT from environment variable (Fly.io sets this to 8080)
# - ${PORT:-8080} = use PORT env var, or default to 8080 if not set
CMD ["sh", "-c", "cd flow && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
