FROM python:3.11-slim-bookworm
ARG VERSION=1.61
RUN pip install --no-cache-dir "holehe==${VERSION}"
WORKDIR /work
ENTRYPOINT ["holehe"]
