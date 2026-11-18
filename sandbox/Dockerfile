FROM python:3.12-slim-bookworm
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright HOME=/home/agent
RUN apt-get update && apt-get install -y --no-install-recommends git curl build-essential nodejs npm \
 && pip install --no-cache-dir fastapi "uvicorn[standard]" playwright \
 && playwright install --with-deps chromium \
 && chmod -R a+rX /ms-playwright \
 && mkdir -p /home/agent && chmod 777 /home/agent \
 && git config --system --add safe.directory '*' \
 && rm -rf /var/lib/apt/lists/*
COPY server.py /srv/server.py
WORKDIR /workspace
CMD ["uvicorn", "server:app", "--app-dir", "/srv", "--host", "0.0.0.0", "--port", "8001"]
