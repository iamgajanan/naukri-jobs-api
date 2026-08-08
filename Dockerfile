FROM mcr.microsoft.com/playwright/python:v1.62.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NAUKRI_HEADLESS=true \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Keep the Playwright runtime image aligned with the pinned Python package.
# The production collector runs headless Chromium; no Xvfb is required.
COPY app ./app
COPY scripts ./scripts

EXPOSE 8000

# Railway injects PORT (currently 8080 for this service). Use a shell so the
# environment variable is expanded at container start.
CMD ["bash", "-lc", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
