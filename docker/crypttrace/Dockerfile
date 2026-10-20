FROM python:3.12-slim-bookworm

# Pinned crypttrace plus its small dependency set. The image exposes only the
# Bitcoin report path; the upstream web extras (Flask) are not installed.
ARG CRYPTTRACE_COMMIT=cf60a88b8be43581186965d160114fdaf3022c62

ENV PYTHONDONTWRITEBYTECODE=1 \
    CRYPTTRACE_HOME=/tmp/crypttrace \
    HOME=/tmp

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && git clone --quiet https://github.com/bobslayerX/crypttrace /opt/crypttrace-src \
    && git -C /opt/crypttrace-src checkout --quiet "${CRYPTTRACE_COMMIT}" \
    && test "$(git -C /opt/crypttrace-src rev-parse HEAD)" = "${CRYPTTRACE_COMMIT}" \
    && pip install --no-cache-dir \
        "typer==0.27.3" \
        "rich==15.0.0" \
        "requests==2.34.2" \
    && pip install --no-cache-dir --no-deps /opt/crypttrace-src \
    && mkdir -p /opt/crypttrace \
    && printf '%s\n' "${CRYPTTRACE_COMMIT}" > /opt/crypttrace/PINNED_COMMIT

COPY run_crypttrace.py /opt/run_crypttrace.py

ENTRYPOINT ["python", "/opt/run_crypttrace.py"]
