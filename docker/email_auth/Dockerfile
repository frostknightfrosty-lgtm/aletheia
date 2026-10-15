FROM python:3.13-slim-bookworm
RUN useradd --create-home --uid 10001 aletheia
# Pin: PyPI JSON API https://pypi.org/pypi/checkdmarc/json -> info.version 6.0.4
# (Apache-2.0, requires-python >=3.10, classifiers include Python 3.14).
# checkdmarc is imported lazily by runner.py; --health never imports it.
RUN pip install --no-cache-dir checkdmarc==6.0.4
COPY runner.py /opt/runner.py
USER aletheia
ENTRYPOINT ["python", "/opt/runner.py"]
