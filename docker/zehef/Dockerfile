FROM python:3.13-slim-bookworm

# The upstream project publishes no releases or tags, so the checkout is
# pinned by commit (config.json "version": 2.2.1, master). The build fails
# unless the checked-out HEAD matches the pin exactly.
ARG ZEHEF_COMMIT=5b0c120efe846eae944dfea9410f925ca3036103

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && git clone --quiet https://github.com/N0rz3/Zehef.git /opt/zehef \
    && git -C /opt/zehef checkout --quiet "${ZEHEF_COMMIT}" \
    && test "$(git -C /opt/zehef rev-parse HEAD)" = "${ZEHEF_COMMIT}" \
    && rm -rf /opt/zehef/.git \
    && printf '%s\n' "${ZEHEF_COMMIT}" > /opt/zehef/PINNED_COMMIT

# Only the third-party runtime dependencies of the modules this driver runs
# are installed, with pinned versions. The upstream requirements.txt also
# names argparse and asyncio, which are standard-library modules on modern
# Python and must not be installed from PyPI.
RUN pip install --no-cache-dir \
    "httpx==0.28.1" \
    "requests==2.32.3" \
    "beautifulsoup4==4.12.3"

COPY run_zehef.py /opt/run_zehef.py

ENV PYTHONPATH=/opt/zehef
WORKDIR /opt/zehef
ENTRYPOINT ["python", "/opt/run_zehef.py"]
