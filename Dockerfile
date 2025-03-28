# Use the official Python base image
FROM python:3.9-slim

# Install FFmpeg (needed for audio conversion)
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set a working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the code
COPY . .

# Expose port 8080 for Cloud Run
ENV PORT 8080
EXPOSE 8080

# Command to run the Flask app with Gunicorn
CMD exec gunicorn main:app --bind 0.0.0.0:$PORT --workers 1 --threads 8
