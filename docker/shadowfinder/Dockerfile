FROM python:3.12-slim-bookworm

# Offline image: pinned ShadowFinder plus its exact lockfile dependency set.
# `timezone_grid.json` is copied out of the checkout so the driver never calls
# the slow grid generator at runtime.
ARG SHADOWFINDER_COMMIT=215485abd5a46a9b98c4ba0fbfce7df6b6bb1be8

ENV PYTHONDONTWRITEBYTECODE=1 \
    MPLCONFIGDIR=/tmp/matplotlib

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && git clone --quiet https://github.com/bellingcat/ShadowFinder /opt/shadowfinder-src \
    && git -C /opt/shadowfinder-src checkout --quiet "${SHADOWFINDER_COMMIT}" \
    && test "$(git -C /opt/shadowfinder-src rev-parse HEAD)" = "${SHADOWFINDER_COMMIT}" \
    && pip install --no-cache-dir \
        "matplotlib==3.10.9" \
        "suncalc==0.1.3" \
        "fire==0.7.1" \
        "pandas==2.3.3" \
        "numpy==2.2.6" \
        "pytz==2025.2" \
        "cartopy==0.24.1" \
        "timezonefinder==6.6.3" \
    && pip install --no-cache-dir --no-deps /opt/shadowfinder-src \
    && mkdir -p /opt/shadowfinder \
    && cp /opt/shadowfinder-src/timezone_grid.json /opt/shadowfinder/timezone_grid.json \
    && rm -rf /opt/shadowfinder-src/.git \
    && printf '%s\n' "${SHADOWFINDER_COMMIT}" > /opt/shadowfinder/PINNED_COMMIT

COPY run_shadowfinder.py /opt/run_shadowfinder.py

ENTRYPOINT ["python", "/opt/run_shadowfinder.py"]
