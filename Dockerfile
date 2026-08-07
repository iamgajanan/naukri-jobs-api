FROM mcr.microsoft.com/playwright/python:v1.62.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NAUKRI_HEADLESS=false \
    DISPLAY=:99

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Keep the Playwright runtime image aligned with the pinned Python package.
# Chromium stays headed while Xvfb supplies the virtual display required by
# server containers such as Railway.
COPY app ./app
COPY scripts ./scripts

EXPOSE 8000

CMD ["bash", "-lc", "Xvfb :99 -screen 0 1440x900x24 -nolisten tcp >/tmp/xvfb.log 2>&1 & exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
