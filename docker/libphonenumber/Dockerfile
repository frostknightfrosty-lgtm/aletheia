FROM python:3.13-slim-bookworm
ARG VERSION=9.0.40
RUN pip install --no-cache-dir "phonenumbers==${VERSION}"
COPY runner.py /opt/runner.py
ENTRYPOINT ["python", "/opt/runner.py"]
