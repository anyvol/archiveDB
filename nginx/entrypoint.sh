#!/bin/sh
set -e

CERT_DIR="/etc/nginx/certs"
CN="${SSL_CERT_CN:-localhost}"
SSL_CERT_IP="${SSL_CERT_IP:-}"
PUBLIC_HTTPS_PORT="${PUBLIC_HTTPS_PORT:-8443}"

if [ "${PUBLIC_HTTPS_PORT}" = "443" ]; then
    REDIRECT_PORT=""
    PUBLIC_URL="https://${CN}/archive/"
else
    REDIRECT_PORT=":${PUBLIC_HTTPS_PORT}"
    PUBLIC_URL="https://${CN}:${PUBLIC_HTTPS_PORT}/archive/"
fi
export REDIRECT_PORT

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

envsubst '${REDIRECT_PORT}' \
    < /etc/nginx/templates/default.conf.template \
    > /etc/nginx/conf.d/default.conf

if [ -n "${SSL_CERT_IP}" ]; then
    cat >> /etc/nginx/conf.d/default.conf <<EOF

# HTTP on LAN IP — no TLS redirect (push requires HTTPS; login and browsing work over HTTP)
server {
    listen 80;
    server_name ${SSL_CERT_IP};

    location = /archive {
        return 302 /archive/;
    }

    location /archive/ {
        proxy_pass http://api:8000/;
        proxy_http_version 1.1;
        proxy_set_header Host \$http_host;
        proxy_set_header X-Forwarded-Host \$http_host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto http;
    }

    location / {
        return 302 /archive/;
    }
}
EOF
    echo "LAN HTTP (no cert): http://${SSL_CERT_IP}/archive/"
fi

echo "nginx listening:"
echo "  http://localhost/archive/          (push works on this PC)"
echo "  https://${CN}${REDIRECT_PORT}/archive/  (LAN — run scripts/windows-forward-ports.ps1 on Windows+WSL)"

exec nginx -g 'daemon off;'
