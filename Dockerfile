FROM python:3.12-slim

# Install system dependencies for grep and find
RUN apt-get update && apt-get install -y \
    grep \
    findutils \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy application file
COPY app.py .

# Install Python dependencies
RUN pip install --no-cache-dir flask

# Create directory for repositories
RUN mkdir -p /repos

# Expose port
EXPOSE 5000

# Set environment variable for Flask
ENV FLASK_APP=app.py

# Run the application
CMD ["python", "app.py"]

