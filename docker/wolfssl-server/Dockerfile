FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y \
    build-essential git autoconf libtool pkg-config \
    ca-certificates curl wget \
    linux-perf

WORKDIR /tmp
RUN git clone --branch v5.8.2-stable --depth 1 https://github.com/wolfSSL/wolfssl.git
WORKDIR /tmp/wolfssl
RUN ./autogen.sh && \
    ./configure --enable-all-crypto --enable-tls13 --enable-experimental --enable-kyber=all --enable-mlkem=yes --enable-benchmark && \
    make -j$(nproc) && \
    make install && \
    ldconfig

ENV LD_LIBRARY_PATH=/usr/local/lib

# Kopiujemy gotowe binarki do ścieżki (prawdziwe binarki, nie skrypty libtool)
RUN cp ./examples/server/.libs/server /usr/local/bin/wolf-server && \
    cp ./examples/client/.libs/client /usr/local/bin/wolf-client && \
    cp ./wolfcrypt/benchmark/.libs/benchmark /usr/local/bin/wolf-benchmark

WORKDIR /
ENTRYPOINT ["sleep", "infinity"]
