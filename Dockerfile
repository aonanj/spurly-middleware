# Use Python 3.12 slim image as base
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    ENVIRONMENT=production

# Set work directory
WORKDIR /app

# Install system dependencies for AI/ML and image processing
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        curl \
        libgl1-mesa-glx \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender-dev \
        libgomp1 \
        libgcc-s1 \
        tesseract-ocr \
        tesseract-ocr-eng \
        git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser \
    && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE $PORT

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:$PORT/health || exit 1

# Command to run the application with gunicorn
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:$PORT --workers 2 --worker-class sync --timeout 300 --keep-alive 2 --max-requests 1000 --max-requests-jitter 100 --preload --access-logfile - --access-logformat '%(h)s %(l)s %(u)s %(t)s \"%(r)s\" %(s)s %(b)s \"%(f)s\" \"%(a)s\"' 'app:create_app()'"]

# Alternative commands for different frameworks:
# For Flask with built-in server (development only):
# CMD ["python", "app.py"]

# For FastAPI with uvicorn:
# CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2"]

# For Django:
# CMD ["sh", "-c", "python manage.py runserver 0.0.0.0:$PORT"]

# For custom Python script:
# CMD ["python", "main.py"]