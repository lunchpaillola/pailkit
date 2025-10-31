# Use Python 3.12 as the base image
# This gives us a clean Linux environment with Python pre-installed
FROM python:3.12-slim

# Set the working directory inside the container
# This is where all our code will live inside the Docker container
WORKDIR /app

# Set environment variables
# PYTHONUNBUFFERED=1 ensures Python output is sent straight to terminal (no buffering)
# This helps with seeing logs in real-time
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Copy the requirements file first
# We do this BEFORE copying the rest of the code because Docker caches each step
# If requirements.txt hasn't changed, Docker can reuse the cached layer (faster builds!)
COPY requirements.txt .

# Install Python dependencies
# pip install --no-cache-dir means don't save the downloaded packages locally (smaller image)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
# This copies everything from the api/ folder (where Dockerfile is) into /app in the container
# The .dockerignore file makes sure we don't copy unnecessary files like tests, cache, etc.
COPY . .

# Expose port 8080
# This tells Docker that our app will be listening on port 8080
# Fly.io will connect to this port
EXPOSE 8080

# Run the FastAPI application using uvicorn
# main:app means "use the 'app' variable from the 'main.py' file"
# --host 0.0.0.0 means listen on all network interfaces (not just localhost)
# --port ${PORT} reads the PORT from environment variable (Fly.io sets this to 8080)
# We default to 8080 if PORT isn't set (useful for local testing)
# Using JSON format for CMD is recommended for proper signal handling
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
