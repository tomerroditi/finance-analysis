# Use an official Python + Node.js base image
FROM python:3.10-slim

# Install required dependencies
RUN apt-get update && apt-get install -y nodejs npm sqlite3 git && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Clone the repo and ensure it exists
RUN rm -rf finance_analysis && git clone https://github.com/tomerroditi/finance-analysis.git /app/finance_analysis

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
#CMD streamlit run main.py --server.port=8501 --server.address=0.0.0.0 && xdg-open http://localhost:8501/
CMD ["streamlit", "run", "main.py", "--server.port=8501", "--server.address=0.0.0.0"]
