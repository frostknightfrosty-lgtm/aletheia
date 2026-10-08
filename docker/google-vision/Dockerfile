FROM python:3.13-slim-bookworm
RUN pip install --no-cache-dir google-cloud-vision==3.16.0
COPY runner.py /opt/runner.py
ENTRYPOINT ["python", "/opt/runner.py"]
