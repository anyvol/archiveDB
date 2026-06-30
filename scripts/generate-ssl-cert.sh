#!/usr/bin/env bash
# Generate a self-signed TLS certificate for local / internal HTTPS.
# Browser push notifications require a secure context (HTTPS or localhost).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERT_DIR="${SCRIPT_DIR}/../nginx/certs"
DAYS="${SSL_CERT_DAYS:-825}"
CN="${SSL_CERT_CN:-localhost}"

mkdir -p "${CERT_DIR}"

if [[ -f "${CERT_DIR}/fullchain.pem" && -f "${CERT_DIR}/privkey.pem" ]]; then
    echo "Certificates already exist in ${CERT_DIR}"
    echo "Delete them first if you want to regenerate."
    exit 0
fi

openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout "${CERT_DIR}/privkey.pem" \
    -out "${CERT_DIR}/fullchain.pem" \
    -days "${DAYS}" \
    -subj "/CN=${CN}"

chmod 644 "${CERT_DIR}/fullchain.pem"
chmod 600 "${CERT_DIR}/privkey.pem"

echo "Generated self-signed certificate in ${CERT_DIR}"
echo "  CN=${CN}, valid for ${DAYS} days"
echo ""
echo "Restart proxy: docker compose up -d proxy"
echo "Open: https://${CN}/archive/"
echo ""
echo "For LAN access, regenerate with your hostname or IP:"
echo "  SSL_CERT_CN=SERVER-PDM ./scripts/generate-ssl-cert.sh"
