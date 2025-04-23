#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PREFIX="$ROOT/local"

OPENSSL_VERSION="3.3.0"
OPENSSL_TARBALL="openssl-${OPENSSL_VERSION}.tar.gz"
OPENSSL_URL="https://www.openssl.org/source/${OPENSSL_TARBALL}"

echo "==> Creating installation prefix at $PREFIX"
mkdir -p "$PREFIX"

if [[ ! -x "$PREFIX/bin/openssl" ]]; then
  echo "==> Downloading OpenSSL ${OPENSSL_VERSION}"
  curl -sSL "$OPENSSL_URL" -o "/tmp/${OPENSSL_TARBALL}"
  tar -xf "/tmp/${OPENSSL_TARBALL}" -C /tmp

  pushd "/tmp/openssl-${OPENSSL_VERSION}" >/dev/null
    echo "==> Configuring and compiling OpenSSL (this may take a few minutes)"
    ./Configure --prefix="$PREFIX" --openssldir="$PREFIX/ssl" \
                enable-ec_nistp_64_gcc_128
    make -j"$(sysctl -n hw.ncpu)"
    make install_sw          
  popd >/dev/null
else
  echo "==> OpenSSL already found in $PREFIX – skipping build"
fi

echo "==> Creating Python virtual environment (.venv)"
python3 -m venv "$ROOT/.venv"

source "$ROOT/.venv/bin/activate"

pip install --upgrade pip wheel

if [[ -f "$ROOT/requirements.txt" ]]; then
  echo "==> Installing Python dependencies from requirements.txt"
  pip install -r "$ROOT/requirements.txt"
fi

echo "✅  Environment is ready."
echo "   To activate later, run:  source .venv/bin/activate"
