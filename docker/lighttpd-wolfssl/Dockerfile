# Dockerfile for lighttpd with wolfSSL + liboqs
ARG LIGHTTPD_VER=1.4.76
ARG WOLFSSL_VER=5.7.0
ARG LIBOQS_VER=0.10.0

FROM alpine:3.19 AS builder
ARG WOLFSSL_VER
ARG LIGHTTPD_VER
ARG LIBOQS_VER

# Install all required dependencies for building in a single layer
RUN apk add --no-cache \
      build-base cmake ninja perl linux-headers git curl \
      pcre2-dev zlib-dev autoconf automake libtool coreutils

WORKDIR /build

# 1. liboqs
RUN git clone --depth 1 -b ${LIBOQS_VER} https://github.com/open-quantum-safe/liboqs.git && \
  cd liboqs && \
  mkdir build && cd build && \
  cmake .. -GNinja -DOQS_USE_OPENSSL=OFF && \
  ninja && ninja install

# 2. wolfSSL with liboqs
RUN git clone --depth 1 -b v${WOLFSSL_VER}-stable https://github.com/wolfssl/wolfssl.git && \
  cd wolfssl && \
  ./autogen.sh && \
  ./configure --prefix=/usr/local \
              --enable-all-crypto \
              --enable-tls13 \
              --with-liboqs \
              --enable-experimental \
              --enable-lighty && \
  make -j$(nproc) && make install

# 3. lighttpd
RUN curl -sSL https://download.lighttpd.net/lighttpd/releases-1.4.x/lighttpd-${LIGHTTPD_VER}.tar.gz | tar -xz && \
  cd lighttpd-${LIGHTTPD_VER} && \
  ./autogen.sh && \
  ./configure --prefix=/usr \
              --with-openssl=no \
              --with-wolfssl \
              --with-zlib && \
  make -j$(nproc) && \
  make install DESTDIR=/build/dist

# ── runtime ────────────────────────────────────────────────────────
FROM alpine:3.19
RUN apk add --no-cache pcre2 zlib
COPY --from=builder /build/dist/usr/sbin/lighttpd /usr/sbin/lighttpd
COPY --from=builder /build/dist/usr/lib /usr/lib
COPY --from=builder /usr/local/lib/libwolfssl.so* /usr/local/lib/
COPY --from=builder /usr/local/lib/liboqs.so* /usr/local/lib/
ENV LD_LIBRARY_PATH=/usr/local/lib:/usr/lib

EXPOSE 4434 4435 4436
CMD ["lighttpd", "-D", "-f", "/etc/lighttpd/lighttpd.conf"] 