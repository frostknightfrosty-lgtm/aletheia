FROM python:3.11-slim-bookworm

# The upstream project publishes no releases or tags, so the checkout is
# pinned by commit (main, 2026-06-28, version 7.0). The build fails unless
# the checked-out HEAD matches the pin exactly.
ARG VENOM_COMMIT=6fa3a483abc9cb0a1d96567e33b2919be59522c6

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && git clone --quiet https://github.com/ghostport-sudo/VENOM.git /opt/venom \
    && git -C /opt/venom checkout --quiet "${VENOM_COMMIT}" \
    && test "$(git -C /opt/venom rev-parse HEAD)" = "${VENOM_COMMIT}" \
    && rm -rf /opt/venom/.git \
    && printf '%s\n' "${VENOM_COMMIT}" > /opt/venom/PINNED_COMMIT

# Pinned runtime dependencies. The upstream list is floor-only
# (aiohttp>=3.8.0, click>=8.0.0, rich>=13.0.0); click is not installed
# because the driver never imports the upstream CLI (venom.py). requests and
# rich are installed because modules/config.py imports them at import time,
# and aiohttp is what every included module actually uses. Versions are
# pinned so they cannot drift under the checkout pin; the module code uses
# only long-stable aiohttp APIs (session.request/get, ClientTimeout,
# ClientConnectorError), so these pins are not version-sensitive.
RUN pip install --no-cache-dir \
    "aiohttp==3.10.11" \
    "requests==2.32.3" \
    "rich==13.9.4"

COPY run_venom.py /opt/run_venom.py

ENV PYTHONPATH=/opt/venom
WORKDIR /opt/venom
ENTRYPOINT ["python", "/opt/run_venom.py"]
