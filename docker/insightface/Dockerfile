FROM python:3.11-slim-bookworm
RUN pip install --no-cache-dir insightface==2.1
COPY runner.py /opt/runner.py
ENV INSIGHTFACE_HOME=/models
ENTRYPOINT ["python", "/opt/runner.py"]
