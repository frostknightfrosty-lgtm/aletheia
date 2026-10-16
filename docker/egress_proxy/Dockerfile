FROM python:3.13-slim-bookworm
RUN useradd --create-home --uid 10001 aletheia
COPY proxy.py /opt/proxy.py
RUN mkdir -p /var/log/aletheia && chown aletheia:aletheia /var/log/aletheia
USER aletheia
EXPOSE 8888
ENTRYPOINT ["python", "/opt/proxy.py"]
