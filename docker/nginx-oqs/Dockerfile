# Dockerfile — Nginx 1.25 + OpenSSL 3.5.0 + liboqs/oqs-provider
ARG OPENSSL_VER=3.5.0
ARG NGINX_VER=1.25.5

FROM alpine:3.19 AS builder
ARG OPENSSL_VER
ARG NGINX_VER

RUN apk add --no-cache \
      build-base perl linux-headers git cmake ninja curl \
      pcre2-dev zlib-dev
WORKDIR /build

# 1. OpenSSL
RUN curl -sSL https://www.openssl.org/source/openssl-${OPENSSL_VER}.tar.gz \
  | tar -xz && cd openssl-${OPENSSL_VER} && \
  ./config shared --prefix=/usr/local/ssl --openssldir=/usr/local/ssl \
                  enable-tls1_3 && \
  make -j$(nproc) && make install_sw
RUN ln -s /usr/local/ssl/lib64 /usr/local/ssl/lib

ENV PATH="/usr/local/ssl/bin:${PATH}" \
    OPENSSL_ROOT_DIR="/usr/local/ssl" \
    LD_LIBRARY_PATH="/usr/local/ssl/lib"

# 2. liboqs
RUN git clone --depth 1 https://github.com/open-quantum-safe/liboqs.git && \
  cmake -S liboqs -B liboqs/build -GNinja \
        -DBUILD_SHARED_LIBS=ON \
        -DCMAKE_INSTALL_PREFIX=/usr/local \
        -DOPENSSL_ROOT_DIR=${OPENSSL_ROOT_DIR} && \
  cmake --build liboqs/build --target install

# 3. oqs-provider
RUN git clone --depth 1 https://github.com/open-quantum-safe/oqs-provider.git && \
  cmake -S oqs-provider -B oqs-provider/build -GNinja \
        -DOPENSSL_ROOT_DIR=${OPENSSL_ROOT_DIR} \
        -DCMAKE_INSTALL_PREFIX=${OPENSSL_ROOT_DIR} && \
  cmake --build oqs-provider/build --target install

# 4. Nginx
RUN curl -sSL http://nginx.org/download/nginx-${NGINX_VER}.tar.gz \
  | tar -xz && cd nginx-${NGINX_VER} && \
  ./configure --prefix=/etc/nginx \
      --with-http_ssl_module --with-http_v2_module \
      --with-cc-opt="-I/usr/local/ssl/include" \
      --with-ld-opt="-L/usr/local/ssl/lib -Wl,-rpath,/usr/local/ssl/lib" && \
  make -j$(nproc) && make install

RUN sed -i '1ienv OPENSSL_CONF;\nenv OPENSSL_MODULES;\nenv LD_LIBRARY_PATH;' \
    /etc/nginx/conf/nginx.conf
RUN sed -i '/http {/a \
    include /etc/nginx/conf.d/*.conf;\n' /etc/nginx/conf/nginx.conf

# ── runtime ────────────────────────────────────────────────────────
FROM alpine:3.19
RUN apk add --no-cache tzdata pcre2 zlib perf
COPY --from=builder /etc/nginx      /etc/nginx
COPY --from=builder /usr/local/ssl  /usr/local/ssl
COPY --from=builder /usr/local/lib  /usr/local/lib
COPY --from=builder /usr/local/ssl/bin/openssl /usr/local/bin/openssl
COPY openssl.cnf /etc/ssl/openssl.cnf
ENV OPENSSL_CONF=/etc/ssl/openssl.cnf
ENV PATH="/etc/nginx/sbin:${PATH}" \
    OPENSSL_MODULES="/usr/local/ssl/lib/ossl-modules" \
    LD_LIBRARY_PATH="/usr/local/ssl/lib:/usr/local/lib"
RUN mkdir -p /etc/nginx/conf.d
EXPOSE 4431 4432 8443
CMD ["nginx", "-g", "daemon off;"]
