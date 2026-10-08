FROM python:3.11-slim-bookworm
ARG VERSION=2.5.6
RUN pip install --no-cache-dir "h8mail==${VERSION}"
WORKDIR /work
ENTRYPOINT ["h8mail"]
