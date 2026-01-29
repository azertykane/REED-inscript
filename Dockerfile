FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    python3-dev \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create directories with proper permissions
RUN mkdir -p static/uploads instance && \
    chmod 755 static/uploads

# Set environment
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 10000

# Run app avec gunicorn et la configuration
CMD ["gunicorn", "--config", "gunicorn.conf.py", "--bind", "0.0.0.0:10000", "app:app"]