# One image for any host that runs containers - Render, Hugging Face Spaces,
# Fly, Railway. Cheaper to maintain than a per-host config file each.
FROM python:3.11-slim

WORKDIR /app

# Dependencies first: this layer is cached unless requirements.txt changes, so
# ordinary code edits do not reinstall the whole stack.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY scripts/ ./scripts/
# The evidence corpus and the cached demo debates ship WITH the image. The demo
# must work when the LLM quota is exhausted, which on a free tier it regularly
# is, so the deployed app serves precomputed debates and needs no API call to
# show anything.
COPY data/ ./data/

ENV PYTHONUNBUFFERED=1 \
    LOG_DIR=/tmp/logs

# Hosts inject the port they want ($PORT). Falling back to 8000 keeps
# `docker run -p 8000:8000` working locally without setting anything.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
