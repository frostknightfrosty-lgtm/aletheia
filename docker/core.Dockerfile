FROM python:3.13-slim-bookworm
WORKDIR /app
COPY pyproject.toml .
COPY app ./app
RUN pip install --no-cache-dir .
USER 10001:10001
ENTRYPOINT ["uvicorn", "aletheia.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
