FROM python:3.13-slim-bookworm
WORKDIR /app
COPY pyproject.toml .
COPY app ./app
RUN pip install --no-cache-dir .
COPY PROJECT_MANIFEST.json /usr/local/lib/python3.13/PROJECT_MANIFEST.json
RUN mkdir -p /data && chown 10001:10001 /data
ENV ALETHEIA_DATA_DIR=/data
VOLUME ["/data"]
USER 10001:10001
ENTRYPOINT ["uvicorn", "aletheia.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
