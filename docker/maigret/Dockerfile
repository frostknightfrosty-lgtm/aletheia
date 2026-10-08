FROM python:3.13-slim-bookworm
ARG VERSION=0.6.6
RUN pip install --no-cache-dir "maigret==${VERSION}"
WORKDIR /work
ENTRYPOINT ["maigret"]
