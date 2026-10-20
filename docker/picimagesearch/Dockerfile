FROM python:3.11-slim-bookworm

# The upstream project's last release tag (v3.9.7, 2023-12-12) predates the
# current network layer (httpx2) and the current engine set, so the checkout
# is pinned by commit (main, 2026-10-10, self-reported version 3.12.11). The
# build fails unless the checked-out HEAD matches the pin exactly.
ARG PICIMAGESEARCH_COMMIT=784713e546273a09aae4b247a8b6f798825efafa

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && git clone --quiet https://github.com/kitUIN/PicImageSearch.git /opt/picimagesearch \
    && git -C /opt/picimagesearch checkout --quiet "${PICIMAGESEARCH_COMMIT}" \
    && test "$(git -C /opt/picimagesearch rev-parse HEAD)" = "${PICIMAGESEARCH_COMMIT}" \
    && pip install --no-cache-dir \
        "httpx2[http2]==2.13.1" \
        "lxml==6.1.3" \
        "pyquery==2.1.0" \
    && pip install --no-cache-dir /opt/picimagesearch \
    && rm -rf /opt/picimagesearch/.git \
    && printf '%s\n' "${PICIMAGESEARCH_COMMIT}" > /opt/picimagesearch/PINNED_COMMIT

COPY run_picimagesearch.py /opt/run_picimagesearch.py

ENTRYPOINT ["python", "/opt/run_picimagesearch.py"]
