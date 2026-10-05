# human-llm - you are the model now.
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY server.py .
COPY static ./static

# The server reads PORT (default 8000) and listens on 0.0.0.0
ENV PORT=8000
EXPOSE 8000

# Session logs land in /app/sessions — mount a volume to keep them:
#   docker run -p 8000:8000 -v "$(pwd)/sessions:/app/sessions" human-llm
CMD ["python", "server.py"]
