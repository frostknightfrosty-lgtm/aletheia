FROM golang:1.26-bookworm
ENV GOTOOLCHAIN=local
RUN go install github.com/projectdiscovery/dnsx/cmd/dnsx@v1.3.1
ENTRYPOINT ["/go/bin/dnsx"]
