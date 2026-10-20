FROM python:3.13-slim-bookworm
RUN useradd --create-home --uid 10001 aletheia
COPY run_minecraft.py /opt/run_minecraft.py
USER aletheia
ENTRYPOINT ["python", "/opt/run_minecraft.py"]
