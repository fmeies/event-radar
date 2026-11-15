FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && curl -fsSL \
       https://github.com/aptible/supercronic/releases/download/v0.2.29/supercronic-linux-amd64 \
       -o /usr/local/bin/supercronic \
    && chmod +x /usr/local/bin/supercronic \
    && apt-get purge -y curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Unprivileged user (uid 1000). It owns /data so that a fresh named volume inherits
# that ownership; an existing volume needs a one-time `chown -R 1000:1000`.
RUN useradd --system --uid 1000 --no-create-home app \
    && mkdir -p /data \
    && chown app:app /data
USER app

# --no-server-header: the reverse proxy passes headers through, so "Server: uvicorn" would reveal the stack
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*", "--no-server-header"]
