FROM golang:1.26-bookworm
ENV GOTOOLCHAIN=local
RUN go install github.com/tomnomnom/assetfinder@v0.1.1
ENTRYPOINT ["/go/bin/assetfinder"]
