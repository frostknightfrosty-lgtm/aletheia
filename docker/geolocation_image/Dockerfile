FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Pins from the projects' official PyPI release pages. The runner uses only
# dfit metadata and steg-analyzer metadata/ELA/histogram paths; it never runs
# extraction or password-cracking commands.
RUN pip install --no-cache-dir dfit-toolkit==1.0.0 steg-analyzer==1.0.1

RUN useradd --create-home --uid 10001 aletheia
COPY runner.py /opt/runner.py
USER aletheia
ENTRYPOINT ["python", "/opt/runner.py"]
