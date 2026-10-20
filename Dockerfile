# traceaudit: service + viewer in one image.
# Stage 1: build the viewer
FROM node:20-alpine AS viewer
WORKDIR /viewer
COPY viewer/package.json viewer/package-lock.json ./
RUN npm ci
COPY viewer/ ./
RUN npm run build

# Stage 2: the service (standard library only at runtime)
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY traceaudit/ ./traceaudit/
RUN pip install --no-cache-dir .
COPY --from=viewer /viewer/dist ./viewer/dist
COPY examples/ ./examples/
COPY data/ ./data/
# Public defaults: visitors may analyse traces and run audits on the site's Anthropic key within the caps below.
ENV TRACEAUDIT_ANONYMOUS=all \
    TRACEAUDIT_ALLOW_CLIENTS=sim,anthropic \
    TRACEAUDIT_OPERATOR_KEYS=anthropic=ANTHROPIC_API_KEY \
    TRACEAUDIT_MAX_CALLS_PER_JOB=200 \
    TRACEAUDIT_MAX_CALLS_PER_DAY=2000 \
    TRACEAUDIT_TOKENS= \
    PORT=8080
EXPOSE 8080
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=4).status==200 else 1)"
CMD ["sh", "-c", "traceaudit serve --root /data --static /app/viewer/dist --host 0.0.0.0 --port ${PORT:-8080} --examples /app/examples ${TRACEAUDIT_TOKENS:+--tokens \"$TRACEAUDIT_TOKENS\"}"]
