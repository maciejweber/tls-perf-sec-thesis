# Dockerfile for lighttpd with OpenSSL (using system libraries)
ARG LIGHTTPD_VER=1.4.76

FROM alpine:3.19 AS builder
ARG LIGHTTPD_VER

# Install dependencies, including system's OpenSSL developer package
RUN apk add --no-cache \
      build-base perl linux-headers git curl \
      pcre2-dev zlib-dev autoconf automake libtool \
      openssl-dev

WORKDIR /build

# Build lighttpd against the system's OpenSSL
RUN curl -sSL https://download.lighttpd.net/lighttpd/releases-1.4.x/lighttpd-${LIGHTTPD_VER}.tar.gz | tar -xz && \
  cd lighttpd-${LIGHTTPD_VER} && \
  ./autogen.sh && \
  ./configure --prefix=/usr \
              --with-openssl \
              --with-zlib && \
  make -j$(nproc) && \
  make install DESTDIR=/build/dist

# ── runtime ────────────────────────────────────────────────────────
FROM alpine:3.19
# Install runtime dependencies, including the system's OpenSSL library
RUN apk add --no-cache pcre2 zlib openssl
COPY --from=builder /build/dist/usr/sbin/lighttpd /usr/sbin/lighttpd
COPY --from=builder /build/dist/usr/lib /usr/lib
ENV LD_LIBRARY_PATH=/usr/lib

EXPOSE 4435
CMD ["lighttpd", "-D", "-f", "/etc/lighttpd/lighttpd.conf"] 