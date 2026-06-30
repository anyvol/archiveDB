#!/bin/sh
set -e

CERT_DIR="/etc/nginx/certs"
CN="${SSL_CERT_CN:-localhost}"
PUBLIC_HTTPS_PORT="${PUBLIC_HTTPS_PORT:-8443}"

if [ "${PUBLIC_HTTPS_PORT}" = "443" ]; then
    REDIRECT_PORT=""
    PUBLIC_URL="https://${CN}/archive/"
else
    REDIRECT_PORT=":${PUBLIC_HTTPS_PORT}"
    PUBLIC_URL="https://${CN}:${PUBLIC_HTTPS_PORT}/archive/"
fi
export REDIRECT_PORT

if [ ! -f "${CERT_DIR}/fullchain.pem" ] || [ ! -f "${CERT_DIR}/privkey.pem" ]; then
    echo "TLS certificate not found — generating self-signed certificate (CN=${CN})..."
    mkdir -p "${CERT_DIR}"
    if ! command -v openssl >/dev/null 2>&1; then
        echo "Installing openssl..."
        apk add --no-cache openssl
    fi
    openssl req -x509 -nodes -newkey rsa:2048 \
        -keyout "${CERT_DIR}/privkey.pem" \
        -out "${CERT_DIR}/fullchain.pem" \
        -days "${SSL_CERT_DAYS:-825}" \
        -subj "/CN=${CN}"
    echo "Certificate created. Open ${PUBLIC_URL} (accept browser security warning for self-signed cert)."
fi

envsubst '${REDIRECT_PORT}' \
    < /etc/nginx/templates/default.conf.template \
    > /etc/nginx/conf.d/default.conf

echo "nginx listening: HTTP :80 -> HTTPS${REDIRECT_PORT:-:443}, app at ${PUBLIC_URL}"

exec nginx -g 'daemon off;'
