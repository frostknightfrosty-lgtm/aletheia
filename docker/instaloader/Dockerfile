FROM python:3.13-slim-bookworm
RUN pip install --no-cache-dir instaloader==4.15.3
COPY runner.py /opt/runner.py
ENTRYPOINT ["python", "/opt/runner.py"]
