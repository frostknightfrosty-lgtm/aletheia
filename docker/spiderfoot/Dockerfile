# SpiderFoot 4.0 meta-adapter image.
#
# The upstream project is pinned to the v4.0.0 release commit so a moved tag
# cannot change the evidence. Only the curated module catalogue in runner.py is
# enabled at scan time; the full module tree is present because SpiderFoot's
# loader imports every module during startup.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/tmp \
    SPIDERFOOT_DATA=/tmp/spiderfoot \
    SPIDERFOOT_LOGS=/tmp/spiderfoot/logs \
    SPIDERFOOT_CACHE=/tmp/spiderfoot/cache

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        git \
        build-essential \
        libffi-dev \
        libssl-dev \
        libxml2-dev \
        libxslt1-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

ARG SPIDERFOOT_REPO=https://github.com/smicallef/spiderfoot.git
ARG SPIDERFOOT_COMMIT=b9c345de5b085debc7444fc10e0e26e7745df5f2

RUN git clone --filter=blob:none "${SPIDERFOOT_REPO}" /opt/spiderfoot \
    && cd /opt/spiderfoot \
    && git checkout --detach "${SPIDERFOOT_COMMIT}" \
    && rm -rf .git

# SpiderFoot 4.0's requirements predate Python 3.11. Keep the upstream
# requirements list, but relax the four constraints that cannot install or
# import on 3.11: PyYAML 5.4.1 has no CPython 3.11 wheel, cryptography <4 and
# pyOpenSSL 21 pre-date 3.11, and NetworkX 2.6 uses removed stdlib aliases.
RUN cd /opt/spiderfoot \
    && sed -i \
        -e 's/pyyaml>=5.4.1,<6/pyyaml>=6.0,<7/' \
        -e 's/cryptography>=3.4.8,<4/cryptography>=41,<42/' \
        -e 's/pyOpenSSL>=21.0.0,<22/pyOpenSSL>=23,<24/' \
        -e 's/networkx>=2.6.3,<2.7/networkx>=2.8,<3/' \
        -e 's/CherryPy>=18.6.1,<19/CherryPy>=18.8,<19/' \
        -e 's/lxml>=4.6.3,<5/lxml>=5,<7/' \
        requirements.txt \
    && python3 -m pip install --upgrade pip \
    && python3 -m pip install -r requirements.txt

COPY runner.py /opt/aletheia/runner.py

RUN useradd --create-home --uid 10001 aletheia \
    && chmod 0755 /opt/aletheia/runner.py

WORKDIR /opt/spiderfoot
USER aletheia

# The Aletheia execution wrapper mounts the work directory at /work and keeps
# the root filesystem read-only. SpiderFoot therefore writes its database,
# cache and logs only under the already-writable /tmp tmpfs.
ENTRYPOINT ["python3", "/opt/aletheia/runner.py"]
