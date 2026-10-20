FROM python:3.12-slim-bookworm

# The pinned checkout is installed without its `streetlevel` dependency on
# purpose: the Google provider walks undocumented internal endpoints and is
# excluded by the source review. The build fails unless HEAD matches the pin.
ARG TRACELINES_COMMIT=99257f0519b30ce7d890db25252f6cf440fa102e

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && git clone --quiet https://github.com/Prekzursil/tracelines.git /opt/tracelines \
    && git -C /opt/tracelines checkout --quiet "${TRACELINES_COMMIT}" \
    && test "$(git -C /opt/tracelines rev-parse HEAD)" = "${TRACELINES_COMMIT}" \
    && pip install --no-cache-dir \
        "aiohttp==3.14.5" \
        "mapbox-vector-tile==2.2.0" \
        "shapely==2.2.0" \
        "networkx==3.7" \
        "diskcache==5.6.3" \
    && pip install --no-cache-dir --no-deps /opt/tracelines \
    && rm -rf /opt/tracelines/.git \
    && printf '%s\n' "${TRACELINES_COMMIT}" > /opt/tracelines/PINNED_COMMIT

COPY run_tracelines.py /opt/run_tracelines.py

ENTRYPOINT ["python", "/opt/run_tracelines.py"]
