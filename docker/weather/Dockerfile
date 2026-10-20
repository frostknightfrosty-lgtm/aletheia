FROM python:3.13-slim-bookworm
RUN useradd --create-home --uid 10001 aletheia
COPY run_weather.py /opt/run_weather.py
USER aletheia
ENTRYPOINT ["python", "/opt/run_weather.py"]
