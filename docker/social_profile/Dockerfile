FROM golang:1.26-bookworm AS slinky-builder
WORKDIR /src
COPY slinky/main.go ./main.go
RUN go mod init aletheia/social-profile-slinky \
    && go get github.com/FurqanSoftware/slinky@e74a138b6bf7264c788871b2e0825455046d09ef \
    && go build -trimpath -o /slinky-profile .

FROM python:3.13-slim-bookworm
RUN useradd --create-home --uid 10001 aletheia \
    && python -m pip install --no-cache-dir crosslinked==0.3.0
COPY --from=slinky-builder /slinky-profile /usr/local/bin/slinky-profile
COPY runner.py /opt/runner.py
USER aletheia
ENTRYPOINT ["python", "/opt/runner.py"]
