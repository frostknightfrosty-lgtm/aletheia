FROM perl:5.40-slim-bookworm
ARG VERSION=13.59
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl tar \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL "https://sourceforge.net/projects/exiftool/files/Image-ExifTool-${VERSION}.tar.gz/download" -o /tmp/exiftool.tar.gz \
    && echo "668ea3acececb7235fbd0f4900e72d5f12c9b07e5c778fd36cb1e9b5828fd65a  /tmp/exiftool.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/exiftool.tar.gz -C /tmp \
    && cd "/tmp/Image-ExifTool-${VERSION}" \
    && cp exiftool /usr/local/bin/exiftool \
    && cp -r lib /usr/local/bin/lib \
    && chmod +x /usr/local/bin/exiftool \
    && rm -rf /tmp/*
WORKDIR /work
ENTRYPOINT ["exiftool"]
