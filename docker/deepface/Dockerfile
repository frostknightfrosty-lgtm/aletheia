FROM python:3.11-slim-bookworm
RUN pip install --no-cache-dir deepface==0.0.101
COPY runner.py /opt/runner.py
ENTRYPOINT ["python", "/opt/runner.py"]
