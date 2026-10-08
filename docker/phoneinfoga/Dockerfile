FROM alpine:3.22
ARG VERSION=2.11.0
ARG TARGETARCH
RUN apk add --no-cache ca-certificates curl tar \
    && case "${TARGETARCH}" in \
         amd64) ARCH=x86_64 ;; \
         arm64) ARCH=arm64 ;; \
         *) echo "Unsupported TARGETARCH=${TARGETARCH}" && exit 1 ;; \
       esac \
    && curl -fsSL "https://github.com/sundowndev/phoneinfoga/releases/download/v${VERSION}/phoneinfoga_Linux_${ARCH}.tar.gz" -o /tmp/phoneinfoga.tar.gz \
    && tar -xzf /tmp/phoneinfoga.tar.gz -C /usr/local/bin \
    && chmod +x /usr/local/bin/phoneinfoga \
    && rm -f /tmp/phoneinfoga.tar.gz
WORKDIR /work
ENTRYPOINT ["phoneinfoga"]
