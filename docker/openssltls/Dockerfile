FROM alpine:3.19 AS build
LABEL org.opencontainers.image.licenses="MIT"

RUN apk add --no-cache build-base perl linux-headers curl

ARG OPENSSL_VER=3.3.3
WORKDIR /build
RUN curl -sSL https://www.openssl.org/source/openssl-${OPENSSL_VER}.tar.gz \
    | tar -xz

WORKDIR /build/openssl-${OPENSSL_VER}

RUN ./config shared --prefix=/usr/local --openssldir=/etc/ssl && \
    make -j$(nproc) && make install_sw

FROM alpine:3.19 AS runtime
LABEL org.opencontainers.image.title="OpenSSL ${OPENSSL_VER} stock"

COPY --from=build /usr/local/bin/openssl /usr/local/bin/openssl

COPY --from=build /usr/local/lib/libcrypto.so.* /usr/local/lib/libssl.so.* /usr/lib/

ENTRYPOINT ["openssl"]
CMD ["version","-a"]
