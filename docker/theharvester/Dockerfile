FROM python:3.14-slim-bookworm
ARG VERSION=4.11.1
RUN pip install --no-cache-dir "https://github.com/laramies/theHarvester/archive/refs/tags/${VERSION}.tar.gz"
WORKDIR /work
ENTRYPOINT ["theHarvester"]
