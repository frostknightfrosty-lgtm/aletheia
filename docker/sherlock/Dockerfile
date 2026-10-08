FROM python:3.12-slim-bookworm
ARG VERSION=0.16.2
RUN pip install --no-cache-dir "sherlock-project==${VERSION}"
WORKDIR /work
ENTRYPOINT ["sherlock"]
