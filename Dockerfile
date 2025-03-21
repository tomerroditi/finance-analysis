# Use an official Python + Node.js base image
FROM python:3.10-slim

# Install required system dependencies (incl. Chromium deps)
RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    sqlite3 \
    git \
    wget \
    gnupg \
    ca-certificates \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxrandr2 \
    libxdamage1 \
    libxfixes3 \
    libx11-xcb1 \
    libxss1 \
    libasound2 \
    libgtk-3-0 \
    libgbm1 \
    fonts-liberation \
    libu2f-udev \
    libdrm2 \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Force fresh clone (disable cache)
ARG CACHE_BUST
RUN echo "Cache Bust: $CACHE_BUST"

# Clone the repo and ensure it exists
RUN rm -rf finance_analysis && \
    git clone https://github.com/tomerroditi/finance-analysis.git /app/finance_analysis

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/finance_analysis/requirements.txt

# Install Node.js dependencies from the correct location
WORKDIR /app/finance_analysis/fad/scraper/node
RUN npm install

# Go back to app root
WORKDIR /app/finance_analysis

# ✅ Ensure the `.streamlit` directory exists
RUN mkdir -p /root/.streamlit

# ✅ Add `secrets.toml` file
RUN echo '[connections.data]\nurl = "sqlite:///fad/resources/data.db"' > /root/.streamlit/secrets.toml

# Expose Streamlit port
EXPOSE 8501

# Run the Streamlit app
CMD ["streamlit", "run", "main.py", "--server.port=8501", "--server.address=0.0.0.0"]
