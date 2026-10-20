FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLCONFIGDIR=/tmp/matplotlib

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ARG PYBD_COMMIT=e2665ee7a6527b9fb0d581bbf7d6dc2914015b02
RUN git clone --filter=blob:none https://github.com/ni1o1/pybdshadow.git /opt/pybdshadow-src \
    && cd /opt/pybdshadow-src \
    && git checkout --detach "${PYBD_COMMIT}" \
    && rm -rf .git

RUN pip install --no-cache-dir \
        "numpy==2.5.4" \
        "pandas==3.0.6" \
        "shapely==2.2.0" \
        "geopandas==1.2.0" \
        "pyproj==3.8.0" \
        "matplotlib==3.11.2" \
        "suncalc==0.1.3" \
        "transbigdata==0.5.3" \
        "vt2geojson==0.2.1" \
        "requests==2.34.2" \
        "tqdm==4.70.1" \
        "retrying==1.4.2" \
    && pip install --no-cache-dir --no-deps /opt/pybdshadow-src

COPY pin.txt /opt/pin.txt
COPY run_pybdshadow.py /opt/run_pybdshadow.py

ENTRYPOINT ["python", "/opt/run_pybdshadow.py"]
