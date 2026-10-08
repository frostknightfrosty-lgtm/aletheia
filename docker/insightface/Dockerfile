FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends libxcb1 libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir insightface==2.1
COPY runner.py /opt/runner.py
ENV INSIGHTFACE_HOME=/models
ENTRYPOINT ["python", "/opt/runner.py"]
