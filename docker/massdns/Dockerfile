FROM debian:bookworm-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git build-essential make && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch v1.1.0 https://github.com/blechschmidt/massdns.git /src/massdns
RUN make -C /src/massdns

FROM debian:bookworm-slim
COPY --from=build /src/massdns/bin/massdns /usr/local/bin/massdns
RUN printf '1.1.1.1\n8.8.8.8\n' > /opt/resolvers.txt
ENTRYPOINT ["/usr/local/bin/massdns"]
