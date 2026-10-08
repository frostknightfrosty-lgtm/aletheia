FROM python:3.13-bookworm
ARG DOCKER_CLI_VERSION=29.1.3
ARG TARGETARCH
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl git bash; \
    rm -rf /var/lib/apt/lists/*; \
    case "${TARGETARCH}" in amd64) DOCKER_ARCH=x86_64 ;; arm64) DOCKER_ARCH=aarch64 ;; *) echo "Unsupported TARGETARCH=${TARGETARCH}" >&2; exit 1 ;; esac; \
    curl -fsSL "https://download.docker.com/linux/static/stable/${DOCKER_ARCH}/docker-${DOCKER_CLI_VERSION}.tgz" -o /tmp/docker.tgz; \
    tar -xzf /tmp/docker.tgz -C /tmp; \
    install -m 0755 /tmp/docker/docker /usr/local/bin/docker; \
    rm -rf /tmp/docker /tmp/docker.tgz
WORKDIR /workspace
COPY pyproject.toml /workspace/pyproject.toml
COPY app /workspace/app
RUN python -m pip install --no-cache-dir \
    'pytest>=9,<10' 'httpx>=0.28,<1' 'fastapi>=0.128,<1' 'pydantic>=2.13,<3' \
    'uvicorn[standard]>=0.40,<1' 'SQLAlchemy>=2.0,<3' 'rapidfuzz==3.14.6' 'reportlab==5.0.1'
