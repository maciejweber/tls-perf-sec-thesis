FROM alpine:3.19 AS build
LABEL org.opencontainers.image.licenses="MIT"
RUN apk add --no-cache build-base cmake git perl python3

WORKDIR /build
RUN git clone --depth 1 https://boringssl.googlesource.com/boringssl
RUN cmake -S boringssl -B out \
          -DCMAKE_BUILD_TYPE=Release \
          -DBUILD_SHARED_LIBS=ON      
RUN cmake --build out --parallel $(nproc)
RUN cmake --install out --prefix /usr/local

FROM alpine:3.19
LABEL org.opencontainers.image.title="BoringSSL latest"
COPY --from=build /usr/local /usr/local
RUN find /usr/local -name '*.a' -delete
ENTRYPOINT ["bash","-c"]
CMD ["openssl version -a"]
