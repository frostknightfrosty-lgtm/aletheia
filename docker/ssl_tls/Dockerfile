# Multi-tool SSL/TLS image: one local CLI per sub-source plus python3 for the runner.
# Base image matches docker/subfinder/Dockerfile so "go install" is available.
FROM golang:1.26-bookworm
ENV GOTOOLCHAIN=local
# Pin: projectdiscovery/tlsx releases page -> https://github.com/projectdiscovery/tlsx/releases/tag/v1.4.0
RUN go install github.com/projectdiscovery/tlsx/cmd/tlsx@v1.4.0
# Pin: lanrat/certgraph releases page -> https://github.com/lanrat/certgraph/releases/tag/v0.1.3
RUN go install github.com/lanrat/certgraph@v0.1.3
# Pins: Debian bookworm testssl.sh 3.0.8+dfsg-1 -> https://packages.debian.org/bookworm/testssl.sh
#        Debian bookworm sslscan 2.0.7-1 -> https://packages.debian.org/bookworm/sslscan
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 sslscan=2.0.7-1 testssl.sh=3.0.8+dfsg-1 \
 && rm -rf /var/lib/apt/lists/*
COPY runner.py /opt/runner.py
ENTRYPOINT ["python3", "/opt/runner.py"]
