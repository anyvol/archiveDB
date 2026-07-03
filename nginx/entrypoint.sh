#!/bin/sh
set -e

CERT_DIR="/etc/nginx/certs"
CN="${SSL_CERT_CN:-localhost}"
SSL_CERT_IP="${SSL_CERT_IP:-}"
PUBLIC_HTTPS_PORT="${PUBLIC_HTTPS_PORT:-8443}"

if [ "${PUBLIC_HTTPS_PORT}" = "443" ]; then
    PUBLIC_URL="https://${CN}/archive/"
else
    PUBLIC_URL="https://${CN}:${PUBLIC_HTTPS_PORT}/archive/"
fi

_build_san() {
    san="DNS:${CN},DNS:localhost,IP:127.0.0.1"
    if [ -n "${SSL_CERT_IP}" ]; then
        san="${san},IP:${SSL_CERT_IP}"
    fi
    printf '%s' "${san}"
}

if [ ! -f "${CERT_DIR}/fullchain.pem" ] || [ ! -f "${CERT_DIR}/privkey.pem" ]; then
    echo "TLS certificate not found — generating self-signed certificate (CN=${CN})..."
    mkdir -p "${CERT_DIR}"
    if ! command -v openssl >/dev/null 2>&1; then
        echo "Installing openssl..."
        apk add --no-cache openssl
    fi
    SAN="$(_build_san)"
    openssl req -x509 -nodes -newkey rsa:2048 \
        -keyout "${CERT_DIR}/privkey.pem" \
        -out "${CERT_DIR}/fullchain.pem" \
        -days "${SSL_CERT_DAYS:-825}" \
        -subj "/CN=${CN}" \
        -addext "subjectAltName=${SAN}"
    echo "Certificate created (SAN=${SAN})."
    echo "Open ${PUBLIC_URL} (accept browser security warning for self-signed cert)."
fi

cp /etc/nginx/templates/default.conf.template /etc/nginx/conf.d/default.conf

echo "nginx listening:"
echo "  http://localhost/archive/          (push works on this PC)"
if [ -n "${SSL_CERT_IP}" ]; then
    echo "  http://${SSL_CERT_IP}/archive/       (LAN — no certificate required)"
fi
if [ "${PUBLIC_HTTPS_PORT}" = "443" ]; then
    echo "  https://${CN}/archive/  (HTTPS + push; run scripts/windows-forward-ports.ps1 on Windows+WSL)"
else
    echo "  https://${CN}:${PUBLIC_HTTPS_PORT}/archive/  (HTTPS + push; run scripts/windows-forward-ports.ps1 on Windows+WSL)"
fi

exec nginx -g 'daemon off;'
