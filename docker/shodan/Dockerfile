FROM python:3.12-slim-bookworm
RUN pip install --no-cache-dir shodan==1.31.0
COPY runner.py /opt/runner.py
ENTRYPOINT ["python", "/opt/runner.py"]
