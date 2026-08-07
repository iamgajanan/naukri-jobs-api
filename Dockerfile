FROM mcr.microsoft.com/playwright/python:v1.54.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NAUKRI_HEADLESS=false \
    DISPLAY=:99

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The Playwright image includes Chromium and Xvfb. Chromium stays in headed
# mode while Xvfb supplies the virtual display required by server containers.
COPY app ./app
COPY scripts ./scripts

EXPOSE 8000

CMD ["bash", "-lc", "Xvfb :99 -screen 0 1440x900x24 -nolisten tcp >/tmp/xvfb.log 2>&1 & exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
