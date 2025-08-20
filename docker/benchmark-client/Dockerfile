# docker/benchmark-client/Dockerfile
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y \
    build-essential git curl zlib1g-dev \
    libssl-dev \
    linux-perf

# Klonowanie i budowanie wrk2
RUN git clone https://github.com/giltene/wrk2.git /wrk2 && \
    cd /wrk2 && \
    make

WORKDIR /wrk2

ENTRYPOINT ["sleep", "infinity"] 