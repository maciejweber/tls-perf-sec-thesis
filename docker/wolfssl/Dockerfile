FROM alpine:3.19 AS build
LABEL org.opencontainers.image.licenses="MIT"
RUN apk add --no-cache build-base cmake git autoconf libtool

WORKDIR /build

RUN git clone --depth 1 https://github.com/open-quantum-safe/liboqs.git
WORKDIR /build/liboqs
RUN mkdir build && cd build && \
    cmake -GNinja -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON .. && \
    ninja install

WORKDIR /build
RUN git clone --branch v5.7.0-stable --depth 1 https://github.com/wolfSSL/wolfssl.git
WORKDIR /build/wolfssl
RUN autoreconf -fi
RUN ./configure --prefix=/usr/local --enable-oqs --enable-opensslextra --enable-quic
RUN make -j$(nproc) && make install

FROM alpine:3.19
LABEL org.opencontainers.image.title="wolfSSL 5.7‑oqs"
COPY --from=build /usr/local /usr/local
RUN find /usr/local -name '*.a' -delete
ENTRYPOINT ["wolfssl","-v"]
