"""Tests for certificate trust script generation."""

from importlib import reload

import app.cert_scripts as cert_scripts_module
import app.config as config_module


class _FakeRequest:
    def __init__(
        self,
        scheme: str = "https",
        host: str = "192.168.4.108:8443",
        forwarded_host: str | None = None,
    ):
        self.url = type("URL", (), {"scheme": scheme, "netloc": host})()
        self.headers = {"host": host, "x-forwarded-proto": scheme}
        if forwarded_host:
            self.headers["x-forwarded-host"] = forwarded_host


def test_cert_download_url_no_double_root_path(monkeypatch):
    monkeypatch.setenv("ROOT_PATH", "/archive")
    monkeypatch.setenv("HTTPS_PORT", "8443")
    reload(config_module)
    reload(cert_scripts_module)

    request = _FakeRequest()
    url = cert_scripts_module.cert_download_url(request)
    assert url == "https://192.168.4.108:8443/archive/cert/fullchain.pem"
    assert "/archive/archive/" not in url


def test_request_host_adds_https_port_when_missing(monkeypatch):
    monkeypatch.setenv("ROOT_PATH", "/archive")
    monkeypatch.setenv("HTTPS_PORT", "8443")
    reload(config_module)
    reload(cert_scripts_module)

    request = _FakeRequest(host="192.168.4.108")
    assert cert_scripts_module.external_base_url(request) == "https://192.168.4.108:8443/archive"


def test_generated_scripts_embed_cert_url():
    cert_url = "https://example.com/archive/cert/fullchain.pem"
    win_cmd = cert_scripts_module.trust_windows_cmd(cert_url)
    assert "ExecutionPolicy Bypass" in win_cmd
    assert cert_url in cert_scripts_module.trust_linux_script(cert_url)
    assert cert_url in cert_scripts_module.trust_macos_script(cert_url)
