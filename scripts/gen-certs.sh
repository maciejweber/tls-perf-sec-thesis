#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# gen-certs.sh — generate demo certificate chain for classical and post-quantum
#                algorithms (RSA-2048, ECDSA-P-256, Ed25519) using OpenSSL 3.x
###############################################################################

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CERT_DIR="${ROOT_DIR}/certs"
mkdir -p "$CERT_DIR"

OPENSSL_BIN="${OPENSSL_BIN:-$ROOT_DIR/local/bin/openssl}"

if [[ -n "${OPENSSL_CNF:-}" ]]; then
  OPENSSL_CNF="$OPENSSL_CNF"
elif [[ -f "$($OPENSSL_BIN version -d | awk -F\" '{print \$2}')/openssl.cnf" ]]; then
  OPENSSL_CNF="$($OPENSSL_BIN version -d | awk -F\" '{print \$2}')/openssl.cnf"
elif [[ -f "/usr/local/etc/openssl@3/openssl.cnf" ]]; then
  OPENSSL_CNF="/usr/local/etc/openssl@3/openssl.cnf"
elif [[ -f "/etc/ssl/openssl.cnf" ]]; then
  OPENSSL_CNF="/etc/ssl/openssl.cnf"
else
  echo "❌ No openssl.cnf found; set OPENSSL_CNF or install OpenSSL@3." >&2
  exit 1
fi

echo "==> Using $($OPENSSL_BIN version | head -1)"
echo "    OpenSSL config: $OPENSSL_CNF"

echo "==> OPENSSL_MODULES is set to: ${OPENSSL_MODULES:-<not set>}"

PASSPHRASE="test"

###############################################################################
# 1.  Local CA (self-signed)
###############################################################################
CA_KEY="$CERT_DIR/ca.key"
CA_CERT="$CERT_DIR/ca.pem"

if [[ ! -f "$CA_KEY" ]]; then
  echo "==> Generating CA key (RSA 4096)"
  "$OPENSSL_BIN" genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 -out "$CA_KEY"
fi

if [[ ! -f "$CA_CERT" ]]; then
  echo "==> Generating CA self-signed certificate"
  "$OPENSSL_BIN" req -config "$OPENSSL_CNF" -x509 -key "$CA_KEY" \
    -subj "/C=PL/O=TLS-Thesis/CN=Local-Demo-CA" \
    -days 3650 -sha256 -out "$CA_CERT"
fi

###############################################################################
# Helper functions
###############################################################################

build() {
  local name="$1"; shift
  local csr="$CERT_DIR/${name}.csr"
  local key="$CERT_DIR/${name}.key"
  local subj="/C=PL/O=TLS-Thesis/CN=${name}"

  echo "==> [${name}] Generating key + CSR"
  "$OPENSSL_BIN" req -config "$OPENSSL_CNF" "$@" \
    -keyout "$key" -out "$csr" -nodes -subj "$subj"
}

sign() {
  local name="$1"
  echo "==> [${name}] Signing with local CA"
  "$OPENSSL_BIN" x509 -req -in "$CERT_DIR/${name}.csr" \
    -CA "$CA_CERT" -CAkey "$CA_KEY" -CAcreateserial \
    -days 825 -sha256 -out "$CERT_DIR/${name}.crt"
}

bundle() {
  local name="$1"
  echo "==> [${name}] Creating PKCS#12 bundle"
  "$OPENSSL_BIN" pkcs12 -export -inkey "$CERT_DIR/${name}.key" \
    -in "$CERT_DIR/${name}.crt" -certfile "$CA_CERT" \
    -out "$CERT_DIR/${name}.p12" -passout pass:"$PASSPHRASE"
}

fingerprint() {
  local name="$1"
  echo "==> [${name}] SHA-256 fingerprint"
  "$OPENSSL_BIN" x509 -in "$CERT_DIR/${name}.crt" -noout -fingerprint -sha256
}

process_alg() {
  local name="$1"; shift
  build "$name" "$@"
  sign "$name"
  bundle "$name"
  fingerprint "$name"
}

###############################################################################
# 2.  Classical algorithms
###############################################################################
process_alg "rsa-2048" -new -newkey rsa:2048
process_alg "ecdsa-p256" -new -newkey ec -pkeyopt ec_paramgen_curve:P-256
process_alg "ed25519" -new -newkey ed25519

echo "✅ All certificates generated in $CERT_DIR (password: $PASSPHRASE)"
