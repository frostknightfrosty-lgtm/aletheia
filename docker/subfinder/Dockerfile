FROM golang:1.26-bookworm
ENV GOTOOLCHAIN=local
RUN go install github.com/projectdiscovery/subfinder/v2/cmd/subfinder@v2.17.0
ENTRYPOINT ["/go/bin/subfinder"]
