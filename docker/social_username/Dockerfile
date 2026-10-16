FROM python:3.13-slim-bookworm
RUN useradd --create-home --uid 10001 aletheia \
    && python -m pip install --no-cache-dir octosuite==5.1.0
COPY runner.py /opt/runner.py
USER aletheia
ENTRYPOINT ["python", "/opt/runner.py"]
