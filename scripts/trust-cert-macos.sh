#!/usr/bin/env bash
# Trust the archive self-signed certificate on macOS.
# Usage: sudo ./trust-cert-macos.sh [/path/to/archive-site.pem]

set -euo pipefail

CERT="${1:-./archive-site.pem}"

if [[ ! -f "${CERT}" ]]; then
    echo "Certificate not found: ${CERT}" >&2
    echo "Download it from Profile → Site certificate setup first." >&2
    exit 1
fi

if [[ "$(id -u)" -ne 0 ]]; then
    echo "Run as root: sudo $0 ${CERT}" >&2
    exit 1
fi

security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain "${CERT}"
echo "Certificate installed. Restart the browser."
