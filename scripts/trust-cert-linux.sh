#!/usr/bin/env bash
# Download and install the archive site certificate (Debian/Ubuntu/Fedora).
#
# Universal usage:
#   sudo ./scripts/trust-cert-linux.sh https://192.168.2.136:8443/archive
#   sudo ./scripts/trust-cert-linux.sh 192.168.2.136 8443
#
# Local file:
#   sudo ./scripts/trust-cert-linux.sh /path/to/fullchain.pem

set -euo pipefail

usage() {
    cat >&2 <<'EOF'
Usage:
  sudo ./trust-cert-linux.sh <server-base-url>
  sudo ./trust-cert-linux.sh <server-host> [https-port] [root-path]
  sudo ./trust-cert-linux.sh /path/to/fullchain.pem

Examples:
  sudo ./trust-cert-linux.sh https://192.168.2.136:8443/archive
  sudo ./trust-cert-linux.sh 192.168.2.136 8443 /archive
EOF
}

if [[ "$(id -u)" -ne 0 ]]; then
    echo "Run as root: sudo $0 $*" >&2
    exit 1
fi

if [[ $# -lt 1 ]]; then
    usage
    exit 1
fi

TEMP=""
cleanup() {
    [[ -n "$TEMP" && -f "$TEMP" ]] && rm -f "$TEMP"
}
trap cleanup EXIT

download_cert() {
    local url="$1"
    local dest="$2"
    curl -fsSk "$url" -o "$dest"
}

fetch_cert_urls() {
    if [[ "$1" == http://* || "$1" == https://* ]]; then
        local base="${1%/}"
        local info_url="${base}/site-info.json"
        local info_file
        info_file="$(mktemp)"
        if download_cert "$info_url" "$info_file"; then
            python3 - "$info_file" <<'PY'
import json, sys
info = json.load(open(sys.argv[1], encoding="utf-8"))
urls = info.get("cert_urls") or []
if not urls and info.get("cert_url"):
    urls = [info["cert_url"]]
for url in urls:
    print(url)
PY
            rm -f "$info_file"
            return 0
        fi
        rm -f "$info_file"
        echo "${base}/cert/fullchain.pem"
        return 0
    fi

    local host="$1"
    local port="${2:-8443}"
    local root="${3:-/archive}"
    root="/${root#/}"
    root="${root%/}"
    if [[ "$port" == "443" || "$port" == "80" ]]; then
        echo "https://${host}${root}/cert/fullchain.pem"
    else
        echo "https://${host}:${port}${root}/cert/fullchain.pem"
    fi
}

if [[ -f "$1" ]]; then
    CERT_FILE="$1"
else
    mapfile -t CERT_URLS < <(fetch_cert_urls "$@")
    TEMP="$(mktemp)"
    downloaded=0
    for cert_url in "${CERT_URLS[@]}"; do
        [[ -z "$cert_url" ]] && continue
        echo "Trying ${cert_url} ..."
        if download_cert "$cert_url" "$TEMP"; then
            echo "Downloaded from ${cert_url}"
            downloaded=1
            break
        fi
    done
    if [[ "$downloaded" -ne 1 ]]; then
        echo "Could not download certificate from server." >&2
        exit 1
    fi
    CERT_FILE="$TEMP"
fi

if command -v update-ca-certificates >/dev/null 2>&1; then
    cp "$CERT_FILE" /usr/local/share/ca-certificates/archive-site.crt
    update-ca-certificates
elif command -v update-ca-trust >/dev/null 2>&1; then
    cp "$CERT_FILE" /etc/pki/ca-trust/source/anchors/archive-site.pem
    update-ca-trust extract
else
    echo "Unsupported distribution. Import ${CERT_FILE} manually." >&2
    exit 1
fi

echo "Done. Restart the browser."
