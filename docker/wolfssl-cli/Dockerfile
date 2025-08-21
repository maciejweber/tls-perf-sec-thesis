FROM alpine:3.19
RUN apk add --no-cache build-base git autoconf automake libtool

RUN git clone --depth 1 --branch v5.8.2-stable https://github.com/wolfSSL/wolfssl.git /wolfssl_src && \
    cd /wolfssl_src && \
    ./autogen.sh && \
    ./configure \
      --enable-tls13 \
      --enable-opensslextra \
      --enable-experimental \
      --enable-curve25519 \
      --enable-kyber=all \
      --enable-mlkem=yes \
      --enable-dilithium \
      --enable-all-asm \
      --enable-debug \
      --enable-aesni \
      --enable-tlsx \
      --enable-keygen \
      --enable-certgen \
      --enable-certreq \
      --prefix=/usr/local && \
    make -j$(nproc) && make install && \
    cp examples/client/.libs/client /usr/local/bin/wolf-client && \
    chmod +x /usr/local/bin/wolf-client

RUN echo "/usr/local/lib" >> /etc/ld-musl-x86_64.path && ldconfig || true
ENV WOLFSSL_HOME=/wolfssl_src
WORKDIR /wolfssl_src

ENTRYPOINT ["sleep", "infinity"]
