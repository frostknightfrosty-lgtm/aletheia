FROM python:3.12-slim-bookworm
RUN pip install --no-cache-dir censys==2.3.0
COPY runner.py /opt/runner.py
ENTRYPOINT ["python", "/opt/runner.py"]
