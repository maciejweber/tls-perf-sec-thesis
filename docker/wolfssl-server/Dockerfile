FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y \
    build-essential git autoconf libtool pkg-config \
    ca-certificates curl wget \
    linux-perf

WORKDIR /tmp
RUN git clone --branch v5.8.0-stable --depth 1 https://github.com/wolfSSL/wolfssl.git
WORKDIR /tmp/wolfssl
RUN ./autogen.sh && \
    ./configure --enable-all-crypto --enable-tls13 --enable-experimental --enable-kyber=all --enable-benchmark && \
    make -j$(nproc)

# Kopiujemy gotowe binarki do ścieżki
RUN cp ./examples/server/server /usr/local/bin/wolf-server && \
    cp ./examples/client/client /usr/local/bin/wolf-client && \
    cp ./wolfcrypt/benchmark/benchmark /usr/local/bin/wolf-benchmark

WORKDIR /
ENTRYPOINT ["sleep", "infinity"]
