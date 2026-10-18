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
 && apt-get install -y --no-install-recommends python3 sslscan testssl.sh openssl git \
 && rm -rf /var/lib/apt/lists/* \
 && dpkg-query -W sslscan testssl.sh python3 openssl
# CipherScan publishes no releases and no tags, so it is pinned by commit (the
# SHA is recorded in docker/ssl_tls/RATE_LIMITS.md and in the runner). The
# build checks the checkout against the exact commit before anything is used
# from it.
ARG CIPHERSCAN_COMMIT=30bd23938853d68b51c2ebe4bcc922cc3113c5e2
RUN git clone https://github.com/mozilla/cipherscan /opt/cipherscan \
 && git -C /opt/cipherscan checkout "${CIPHERSCAN_COMMIT}" \
 && test "$(git -C /opt/cipherscan rev-parse HEAD)" = "${CIPHERSCAN_COMMIT}" \
 && rm -rf /opt/cipherscan/.git
# cscan.sh -- the "more precise scan" CipherScan runs in its tolerance section
# (test_tls_tolerance) -- would otherwise clone tlslite-ng and python-ecdsa
# UNPINNED from GitHub at run time. Both are pre-provisioned here at pinned
# releases instead, in exactly the layout cscan.sh expects (a "tlslite" and an
# "ecdsa" directory importable from the repository root; the two symlinks
# mirror the ones cscan.sh itself creates). The SHAs are recorded in
# docker/ssl_tls/RATE_LIMITS.md.
ARG TLSLITE_NG_COMMIT=c93df82603ab4a72c8d65645a3aeee73eeb24b3f
ARG PYTHON_ECDSA_COMMIT=bd66899550d7185939bf27b75713a2ac9325a9d3
RUN git clone https://github.com/tomato42/tlslite-ng /opt/cipherscan/.tlslite-ng \
 && git -C /opt/cipherscan/.tlslite-ng checkout "${TLSLITE_NG_COMMIT}" \
 && test "$(git -C /opt/cipherscan/.tlslite-ng rev-parse HEAD)" = "${TLSLITE_NG_COMMIT}" \
 && rm -rf /opt/cipherscan/.tlslite-ng/.git \
 && git clone https://github.com/warner/python-ecdsa /opt/cipherscan/.python-ecdsa \
 && git -C /opt/cipherscan/.python-ecdsa checkout "${PYTHON_ECDSA_COMMIT}" \
 && test "$(git -C /opt/cipherscan/.python-ecdsa rev-parse HEAD)" = "${PYTHON_ECDSA_COMMIT}" \
 && rm -rf /opt/cipherscan/.python-ecdsa/.git \
 && ln -s .tlslite-ng/tlslite /opt/cipherscan/tlslite \
 && ln -s .python-ecdsa/src/ecdsa /opt/cipherscan/ecdsa
COPY runner.py /opt/runner.py
ENTRYPOINT ["python3", "/opt/runner.py"]
