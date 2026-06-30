#!/usr/bin/env bash
# Generate a self-signed TLS certificate for local / internal HTTPS.
# Browser push notifications require a secure context (HTTPS or localhost).
#
# Usage:
#   SSL_CERT_CN=SERVER-PDM SSL_CERT_IP=192.168.4.108 ./scripts/generate-ssl-cert.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERT_DIR="${SCRIPT_DIR}/../nginx/certs"
DAYS="${SSL_CERT_DAYS:-825}"
CN="${SSL_CERT_CN:-localhost}"
IP="${SSL_CERT_IP:-}"

mkdir -p "${CERT_DIR}"

if [[ -f "${CERT_DIR}/fullchain.pem" && -f "${CERT_DIR}/privkey.pem" ]]; then
    echo "Certificates already exist in ${CERT_DIR}"
    echo "Delete them first if you want to regenerate:"
    echo "  rm -f nginx/certs/*.pem"
    exit 0
fi

SAN="DNS:${CN},DNS:localhost,IP:127.0.0.1"
if [[ -n "${IP}" ]]; then
    SAN="${SAN},IP:${IP}"
fi

openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout "${CERT_DIR}/privkey.pem" \
    -out "${CERT_DIR}/fullchain.pem" \
    -days "${DAYS}" \
    -subj "/CN=${CN}" \
    -addext "subjectAltName=${SAN}"

chmod 644 "${CERT_DIR}/fullchain.pem"
chmod 600 "${CERT_DIR}/privkey.pem"

echo "Generated self-signed certificate in ${CERT_DIR}"
echo "  CN=${CN}"
echo "  SAN=${SAN}"
echo "  valid for ${DAYS} days"
echo ""
echo "Restart proxy: docker compose up -d proxy"
echo ""
echo "Browsers will still show «Not secure» until the certificate is trusted."
echo "On Windows clients run (as Administrator):"
echo "  .\\scripts\\trust-cert-windows.ps1 -CertPath \\\\SERVER-PDM\\share\\fullchain.pem"
echo "  # or copy nginx/certs/fullchain.pem and trust locally"
