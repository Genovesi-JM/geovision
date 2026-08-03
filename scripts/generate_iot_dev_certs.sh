#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CERT_DIR="$ROOT_DIR/.iot/certs"
mkdir -p "$CERT_DIR"
if [ -s "$CERT_DIR/ca.crt" ] && [ -s "$CERT_DIR/server.crt" ] && [ -s "$CERT_DIR/server.key" ]; then
  exit 0
fi
openssl req -x509 -newkey rsa:2048 -days 3650 -nodes -subj "/CN=GeoVision Development CA" -keyout "$CERT_DIR/ca.key" -out "$CERT_DIR/ca.crt"
openssl req -newkey rsa:2048 -nodes -subj "/CN=localhost" -keyout "$CERT_DIR/server.key" -out "$CERT_DIR/server.csr"
EXT_FILE="$CERT_DIR/server.ext"
printf '%s\n' 'subjectAltName=DNS:localhost,DNS:mqtt,IP:127.0.0.1' > "$EXT_FILE"
openssl x509 -req -in "$CERT_DIR/server.csr" -CA "$CERT_DIR/ca.crt" -CAkey "$CERT_DIR/ca.key" -CAcreateserial -days 825 -extfile "$EXT_FILE" -out "$CERT_DIR/server.crt"
chmod 600 "$CERT_DIR"/*.key
