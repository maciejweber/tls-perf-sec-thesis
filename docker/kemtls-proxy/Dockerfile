FROM golang:1.22-alpine AS build
RUN apk add --no-cache git
WORKDIR /src
RUN git clone --depth 1 https://github.com/cloudflare/kemtls.git .
RUN CGO_ENABLED=0 go build -o /out/kemtls-proxy ./cmd/kemtls-proxy

FROM alpine:3.19
COPY --from=build /out/kemtls-proxy /usr/local/bin/kemtls-proxy
ENTRYPOINT ["kemtls-proxy"]
