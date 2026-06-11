FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Make the entrypoint executable, then drop to a non-root user.
RUN chmod +x entrypoint.sh \
    && useradd -m -u 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

# entrypoint.sh runs migrations (when RUN_MIGRATIONS=true) then execs the CMD.
# --proxy-headers so the real client IP (for rate limiting) is read from the
# proxy; $PORT lets hosts that assign their own port work unchanged.
ENTRYPOINT ["./entrypoint.sh"]
# Bind to :: (IPv6, dual-stack — also serves IPv4 on Linux). Required for Railway
# private networking, which is IPv6-only; harmless for the IPv4 compose stack.
CMD ["sh", "-c", "uvicorn app.main:app --host :: --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --proxy-headers"]
