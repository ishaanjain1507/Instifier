FROM python:3.10-slim

# Install OS dependencies in one layer and clean up
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget gnupg unzip \
    libnss3 libxss1 libasound2 libatk1.0-0 libatk-bridge2.0-0 \
    libgtk-3-0 libgbm-dev libdrm2 libx11-xcb1 libxcb-dri3-0 \
 && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install only Chromium for Playwright (omit Firefox/WebKit)
RUN playwright install --with-deps chromium

# Copy source files
COPY . .

# Port
EXPOSE 8000

# Start server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
