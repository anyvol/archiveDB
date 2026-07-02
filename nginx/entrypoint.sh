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

_ensure_openssl() {
    if ! command -v openssl >/dev/null 2>&1; then
        echo "Installing openssl..."
        apk add --no-cache openssl
    fi
}

_cert_text() {
    if [ ! -f "${CERT_DIR}/fullchain.pem" ]; then
        return 1
    fi
    openssl x509 -in "${CERT_DIR}/fullchain.pem" -noout -text 2>/dev/null
}

_cert_matches_env() {
    cert_text="$(_cert_text)" || return 1
    printf '%s\n' "${cert_text}" | grep -Fq "DNS:${CN}" || return 1
    if [ -n "${SSL_CERT_IP}" ]; then
        printf '%s\n' "${cert_text}" | grep -Fq "IP Address:${SSL_CERT_IP}" || return 1
    fi
    return 0
}

_generate_certificate() {
    reason="$1"
    echo "${reason}"
    mkdir -p "${CERT_DIR}"
    _ensure_openssl
    SAN="$(_build_san)"
    openssl req -x509 -nodes -newkey rsa:2048 \
        -keyout "${CERT_DIR}/privkey.pem" \
        -out "${CERT_DIR}/fullchain.pem" \
        -days "${SSL_CERT_DAYS:-825}" \
        -subj "/CN=${CN}" \
        -addext "subjectAltName=${SAN}"
    echo "Certificate created (SAN=${SAN})."
    echo "Open ${PUBLIC_URL} (run trust-windows.cmd on client PCs after regenerating)."
}

if [ ! -f "${CERT_DIR}/fullchain.pem" ] || [ ! -f "${CERT_DIR}/privkey.pem" ]; then
    _generate_certificate "TLS certificate not found — generating self-signed certificate (CN=${CN})..."
elif ! _cert_matches_env; then
    echo "Existing certificate does not match SSL_CERT_CN=${CN} / SSL_CERT_IP=${SSL_CERT_IP}."
    rm -f "${CERT_DIR}/fullchain.pem" "${CERT_DIR}/privkey.pem"
    _generate_certificate "Regenerating self-signed certificate with updated SAN..."
fi

envsubst '${REDIRECT_PORT}' \
    < /etc/nginx/templates/default.conf.template \
    > /etc/nginx/conf.d/default.conf

echo "nginx listening:"
echo "  http://localhost/archive/          (push works on this PC)"
echo "  https://${CN}${REDIRECT_PORT}/archive/  (LAN — run scripts/windows-forward-ports.ps1 on Windows+WSL)"
if [ -n "${SSL_CERT_IP}" ]; then
    echo "  https://${SSL_CERT_IP}${REDIRECT_PORT}/archive/"
fi

exec nginx -g 'daemon off;'
