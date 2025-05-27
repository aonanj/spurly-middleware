# Use Python 3.12 slim image as base
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        curl \
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

# Command to run the application
# Adjust this based on your specific application entry point
# Replace the CMD line with:
CMD ["sh", "-c", "python -m gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 app:app"]

# Alternative commands for different frameworks:
# For Flask with built-in server (development only):
# CMD ["python", "app.py"]

# For FastAPI with uvicorn:
# CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2"]

# For Django:
# CMD ["sh", "-c", "python manage.py runserver 0.0.0.0:$PORT"]

# For custom Python script:
# CMD ["python", "main.py"]