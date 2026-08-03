FROM python:3.9-slim

# Install system dependencies for pyzbar
RUN apt-get update && \
    apt-get install -y libzbar0 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

# Create an empty users.json if it doesn't exist so it can persist state
RUN echo "{}" > users.json

CMD ["python", "bot.py"]
