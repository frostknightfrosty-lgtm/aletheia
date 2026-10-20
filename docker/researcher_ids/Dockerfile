FROM python:3.13-slim-bookworm
RUN useradd --create-home --uid 10001 aletheia
COPY run_researcher_ids.py /opt/run_researcher_ids.py
USER aletheia
ENTRYPOINT ["python", "/opt/run_researcher_ids.py"]
