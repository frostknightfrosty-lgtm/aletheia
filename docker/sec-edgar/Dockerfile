FROM python:3.13-slim
RUN useradd --create-home --uid 10001 aletheia
WORKDIR /work
COPY runner.py /opt/runner.py
USER aletheia
ENTRYPOINT ["python", "/opt/runner.py"]
