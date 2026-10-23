FROM golang:1.26-bookworm
ENV GOTOOLCHAIN=local
ENV TMPDIR=/work
RUN mkdir -p /work /tmp && chmod 777 /work /tmp
RUN go install github.com/owasp-amass/amass/v5/cmd/amass@v5.1.1
ENTRYPOINT ["/go/bin/amass"]
