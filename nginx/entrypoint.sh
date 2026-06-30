#!/bin/sh
set -e

CERT_DIR="/etc/nginx/certs"
CN="${SSL_CERT_CN:-localhost}"

if [ ! -f "${CERT_DIR}/fullchain.pem" ] || [ ! -f "${CERT_DIR}/privkey.pem" ]; then
    echo "TLS certificate not found — generating self-signed certificate (CN=${CN})..."
    mkdir -p "${CERT_DIR}"
    openssl req -x509 -nodes -newkey rsa:2048 \
        -keyout "${CERT_DIR}/privkey.pem" \
        -out "${CERT_DIR}/fullchain.pem" \
        -days "${SSL_CERT_DAYS:-825}" \
        -subj "/CN=${CN}"
    echo "Certificate created. Open https://${CN}/archive/ (accept browser security warning for self-signed cert)."
fi

exec nginx -g 'daemon off;'
