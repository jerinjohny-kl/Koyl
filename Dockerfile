FROM python:3.10-slim

WORKDIR /app

# Install dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    aria2 \
    qbittorrent-nox \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all files
COPY . .

# Ensure start script is executable
RUN chmod +x start.sh

# Expose port for Koyeb healthcheck
EXPOSE 8000

CMD ["./start.sh"]
