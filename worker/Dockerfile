FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Scrapegraph CLI (mounted at /scrapegraph) needs 3.12+ plus collector extras
# and Chromium. First build is large/slow — expected (Playwright + browser).
RUN pip install --no-cache-dir "scrapegraphai[collector]" \
    && playwright install --with-deps chromium

COPY scrapegraph_worker/ ./scrapegraph_worker/
COPY data/ ./data/

# The actual Scrapegraph repo is mounted at runtime (see docker-compose.yml)
# rather than baked into this image, so scraping logic changes don't require
# rebuilding the worker image.
ENV SCRAPEGRAPH_REPO_PATH=/scrapegraph

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"

CMD ["uvicorn", "scrapegraph_worker.api:app", "--host", "0.0.0.0", "--port", "8000"]
