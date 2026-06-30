#!/usr/bin/env bash
# Trust the archive self-signed certificate on Linux (Debian/Ubuntu/Fedora).
# Usage: sudo ./trust-cert-linux.sh [/path/to/archive-site.pem]

set -euo pipefail

CERT="${1:-./archive-site.pem}"

if [[ ! -f "${CERT}" ]]; then
    echo "Certificate not found: ${CERT}" >&2
    echo "Download it from Profile → Site certificate setup, or:" >&2
    echo "  curl -k -b cookies.txt -o archive-site.pem https://SERVER:8443/archive/cert/fullchain.pem" >&2
    exit 1
fi

if [[ "$(id -u)" -ne 0 ]]; then
    echo "Run as root: sudo $0 ${CERT}" >&2
    exit 1
fi

if command -v update-ca-certificates >/dev/null 2>&1; then
    cp "${CERT}" /usr/local/share/ca-certificates/archive-site.crt
    update-ca-certificates
    echo "Certificate installed. Restart the browser."
elif command -v update-ca-trust >/dev/null 2>&1; then
    cp "${CERT}" /etc/pki/ca-trust/source/anchors/archive-site.pem
    update-ca-trust extract
    echo "Certificate installed. Restart the browser."
else
    echo "Unsupported distribution. Import ${CERT} into your browser or system trust store manually." >&2
    exit 1
fi
