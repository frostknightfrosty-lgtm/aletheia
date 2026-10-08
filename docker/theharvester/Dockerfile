FROM python:3.14-slim-bookworm
ARG VERSION=4.11.1
RUN pip install --no-cache-dir "theHarvester==${VERSION}"
WORKDIR /work
ENTRYPOINT ["theHarvester"]
