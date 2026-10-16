FROM python:3.13-slim-bookworm
RUN useradd --create-home --uid 10001 aletheia
COPY runner.py /opt/runner.py
USER aletheia
ENTRYPOINT ["python", "/opt/runner.py"]
