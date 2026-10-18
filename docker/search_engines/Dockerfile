FROM python:3.13-slim-bookworm

# SearXNG is installed from the exact upstream commit pinned in the runner
# (SEARXNG_PINNED_COMMIT) and in RATE_LIMITS.md, using the official
# source-install sequence from docs.searxng.org (installation-searxng):
# system build deps, then the documented bootstrap packages, then
# `pip install --use-pep517 --no-build-isolation -e .`.
ARG SEARXNG_COMMIT=1c10abe2d3e4ab7ddcc4e9da1a7d07dc7ca7f8f4
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git build-essential libxslt1-dev zlib1g-dev libffi-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/searxng/searxng /opt/searxng \
    && git -C /opt/searxng checkout "${SEARXNG_COMMIT}" \
    && test "$(git -C /opt/searxng rev-parse HEAD)" = "${SEARXNG_COMMIT}" \
    && rm -rf /opt/searxng/.git
RUN pip install --no-cache-dir -U pip setuptools wheel \
    && pip install --no-cache-dir -U pyyaml msgspec typing-extensions pybind11 \
    && pip install --no-cache-dir --use-pep517 --no-build-isolation -e /opt/searxng
RUN useradd --create-home --uid 10001 aletheia \
    && chown -R aletheia:aletheia /opt/searxng
COPY runner.py /opt/runner.py
ENV PYTHONDONTWRITEBYTECODE=1
USER aletheia
ENTRYPOINT ["python", "/opt/runner.py"]
