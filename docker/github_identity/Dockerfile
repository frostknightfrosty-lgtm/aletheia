FROM python:3.13-slim-bookworm
RUN useradd --create-home --uid 10001 aletheia
COPY run_github_identity.py /opt/run_github_identity.py
USER aletheia
ENTRYPOINT ["python", "/opt/run_github_identity.py"]
