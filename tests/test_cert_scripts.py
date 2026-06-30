"""Tests for certificate trust script generation."""

from app.cert_scripts import (
    cert_download_url,
    trust_linux_script,
    trust_macos_script,
    trust_windows_cmd,
)


class _FakeRequest:
    def __init__(self, scheme: str = "https", host: str = "192.168.4.108:8443"):
        self.url = type("URL", (), {"scheme": scheme, "netloc": host})()
        self.headers = {"host": host, "x-forwarded-proto": scheme}


def test_cert_download_url_uses_forwarded_proto():
    request = _FakeRequest()
    url = cert_download_url(request)
    assert url.startswith("https://192.168.4.108:8443")
    assert url.endswith("/cert/fullchain.pem")


def test_generated_scripts_embed_cert_url():
    cert_url = "https://example.com/archive/cert/fullchain.pem"
    win_cmd = trust_windows_cmd(cert_url)
    assert cert_url in win_cmd or "EncodedCommand" in win_cmd
    assert "ExecutionPolicy Bypass" in win_cmd
    assert cert_url in trust_linux_script(cert_url)
    assert cert_url in trust_macos_script(cert_url)
    assert "curl -fsSk" in trust_linux_script(cert_url)
