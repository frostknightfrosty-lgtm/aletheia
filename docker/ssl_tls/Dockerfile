# Multi-tool SSL/TLS image: one local CLI per sub-source plus python3 for the runner.
# Base image matches docker/subfinder/Dockerfile so "go install" is available.
FROM golang:1.26-bookworm
ENV GOTOOLCHAIN=local
# Pin: projectdiscovery/tlsx releases page -> https://github.com/projectdiscovery/tlsx/releases/tag/v1.4.0
RUN go install github.com/projectdiscovery/tlsx/cmd/tlsx@v1.4.0
# Pin: lanrat/certgraph releases page -> https://github.com/lanrat/certgraph/releases/tag/v0.1.3
RUN go install github.com/lanrat/certgraph@v0.1.3
# Debian packages for testssl.sh and sslscan are installed UNPINNED.
# An exact version pin was tried first and failed in CI run 38669069783:
#   E: Version '2.0.7-1' for 'sslscan' was not found
# even though sources.debian.org lists 2.0.7-1 in bookworm (and 3.0.8+dfsg-1 for testssl.sh).
# This base image's apt sources therefore do not resolve those exact versions, so the pin is not
# reproducible here. The resolved versions are echoed into the build log instead, so every CI run
# records exactly what was installed. Upstream latest for reference:
#   testssl.sh https://github.com/testssl/testssl.sh/releases  |  sslscan https://github.com/rbsec/sslscan/releases
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 sslscan testssl.sh \
 && rm -rf /var/lib/apt/lists/* \
 && dpkg-query -W sslscan testssl.sh python3
COPY runner.py /opt/runner.py
ENTRYPOINT ["python3", "/opt/runner.py"]
