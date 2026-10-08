FROM perl:5.40-slim-bookworm
ARG VERSION=13.59
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl tar \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL "https://exiftool.org/Image-ExifTool-${VERSION}.tar.gz" -o /tmp/exiftool.tar.gz \
    && tar -xzf /tmp/exiftool.tar.gz -C /tmp \
    && cd "/tmp/Image-ExifTool-${VERSION}" \
    && cp exiftool /usr/local/bin/exiftool \
    && cp -r lib /usr/local/bin/lib \
    && chmod +x /usr/local/bin/exiftool \
    && rm -rf /tmp/*
WORKDIR /work
ENTRYPOINT ["exiftool"]
