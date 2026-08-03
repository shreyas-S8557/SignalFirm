FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scrapegraph_worker/ ./scrapegraph_worker/

# The actual Scrapegraph repo is mounted at runtime (see docker-compose.yml)
# rather than baked into this image, so scraping logic changes don't require
# rebuilding the worker image.
ENV SCRAPEGRAPH_REPO_PATH=/scrapegraph

EXPOSE 8000

CMD ["uvicorn", "scrapegraph_worker.api:app", "--host", "0.0.0.0", "--port", "8000"]
