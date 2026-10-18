FROM python:3.11-slim-bookworm

# The upstream project publishes no releases or tags, so the checkout is
# pinned by commit (main, 2024-03-11, version 2.0.4). The build fails unless
# the checked-out HEAD matches the pin exactly.
ARG TIKTOK_COMMIT=2a4af674efc4af7c7d592053ec3f475555f37694

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && git clone --quiet https://github.com/bellingcat/tiktok-hashtag-analysis.git /opt/tiktok \
    && git -C /opt/tiktok checkout --quiet "${TIKTOK_COMMIT}" \
    && test "$(git -C /opt/tiktok rev-parse HEAD)" = "${TIKTOK_COMMIT}" \
    && rm -rf /opt/tiktok/.git \
    && printf '%s\n' "${TIKTOK_COMMIT}" > /opt/tiktok/PINNED_COMMIT

# Pinned runtime dependencies (March 2024 era, matching the checkout). The
# pinned client declares only requests and playwright; the rest are the
# checkout's own runtime imports (setup.py), installed explicitly so the
# versions cannot drift under the pin. Python 3.11 is used because
# playwright 1.42.0 has no wheels for newer interpreters.
RUN pip install --no-cache-dir \
    "TikTokApi==6.2.2" \
    "playwright==1.42.0" \
    "tenacity==8.2.3" \
    "requests==2.31.0" \
    "yt_dlp==2024.3.10" \
    "matplotlib==3.8.3" \
    "seaborn==0.13.2" \
    "numpy==1.26.4" \
    "pandas==2.2.1"

# Playwright's Chromium with its system dependencies. Headless use only; the
# driver never passes headed=True.
RUN python -m playwright install --with-deps chromium

COPY run_tiktok_hashtag.py /opt/run_tiktok_hashtag.py

ENV PYTHONPATH=/opt/tiktok
WORKDIR /opt/tiktok
ENTRYPOINT ["python", "/opt/run_tiktok_hashtag.py"]
