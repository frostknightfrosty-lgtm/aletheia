FROM python:3.13-slim-bookworm
RUN useradd --create-home --uid 10001 aletheia
COPY run_pgp_keys.py /opt/run_pgp_keys.py
USER aletheia
ENTRYPOINT ["python", "/opt/run_pgp_keys.py"]
