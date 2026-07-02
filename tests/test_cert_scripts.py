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


def _reload_modules(monkeypatch, **env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    reload(config_module)
    reload(cert_scripts_module)


def test_cert_download_url_no_double_root_path(monkeypatch):
    _reload_modules(monkeypatch, ROOT_PATH="/archive", HTTPS_PORT="8443")

    request = _FakeRequest()
    url = cert_scripts_module.cert_download_url(request)
    assert url == "https://192.168.4.108:8443/archive/cert/fullchain.pem"
    assert "/archive/archive/" not in url


def test_cert_download_url_uses_https_even_when_profile_opened_over_http(monkeypatch):
    _reload_modules(monkeypatch, ROOT_PATH="/archive", HTTPS_PORT="8443")

    request = _FakeRequest(scheme="http", host="192.168.2.136:8080")
    url = cert_scripts_module.cert_download_url(request)
    assert url == "https://192.168.2.136:8443/archive/cert/fullchain.pem"


def test_cert_download_url_prefers_ssl_cert_ip_for_localhost(monkeypatch):
    _reload_modules(
        monkeypatch,
        ROOT_PATH="/archive",
        HTTPS_PORT="8443",
        SSL_CERT_IP="192.168.2.136",
        SSL_CERT_CN="WIN-TVA",
    )

    request = _FakeRequest(scheme="http", host="localhost:8080")
    url = cert_scripts_module.cert_download_url(request)
    assert url == "https://192.168.2.136:8443/archive/cert/fullchain.pem"


def test_cert_url_candidates_include_ip_and_hostname(monkeypatch):
    _reload_modules(
        monkeypatch,
        ROOT_PATH="/archive",
        HTTPS_PORT="8443",
        SSL_CERT_IP="192.168.2.136",
        SSL_CERT_CN="WIN-TVA",
    )

    request = _FakeRequest(scheme="http", host="localhost:8080")
    urls = cert_scripts_module.cert_url_candidates(request)
    assert urls[0] == "https://192.168.2.136:8443/archive/cert/fullchain.pem"
    assert "https://WIN-TVA:8443/archive/cert/fullchain.pem" in urls
    assert "https://localhost:8443/archive/cert/fullchain.pem" in urls


def test_server_site_info_contains_public_metadata(monkeypatch):
    _reload_modules(
        monkeypatch,
        ROOT_PATH="/archive",
        HTTPS_PORT="8443",
        SSL_CERT_IP="192.168.2.136",
        SSL_CERT_CN="WIN-TVA",
    )

    request = _FakeRequest(scheme="http", host="localhost:8080")
    info = cert_scripts_module.server_site_info(request)
    assert info["public_host"] == "192.168.2.136"
    assert info["https_port"] == 8443
    assert info["root_path"] == "/archive"
    assert info["cert_cn"] == "WIN-TVA"
    assert info["cert_ip"] == "192.168.2.136"
    assert info["base_url"] == "https://192.168.2.136:8443/archive"
    assert info["cert_url"] == info["cert_urls"][0]


def test_request_host_adds_https_port_when_missing(monkeypatch):
    _reload_modules(monkeypatch, ROOT_PATH="/archive", HTTPS_PORT="8443")

    request = _FakeRequest(host="192.168.4.108")
    assert cert_scripts_module.external_base_url(request) == "https://192.168.4.108:8443/archive"


def test_generated_scripts_embed_server_candidates(monkeypatch):
    _reload_modules(
        monkeypatch,
        ROOT_PATH="/archive",
        HTTPS_PORT="8443",
        SSL_CERT_IP="192.168.2.136",
        SSL_CERT_CN="WIN-TVA",
    )

    request = _FakeRequest(scheme="http", host="localhost:8080")
    info = cert_scripts_module.server_site_info(request)
    win_cmd = cert_scripts_module.trust_windows_cmd(info)
    win_ps1 = cert_scripts_module.trust_windows_ps1(info)
    assert "EncodedCommand" not in win_cmd
    assert "certutil -addstore -f Root" in win_cmd
    assert "curl.exe -fsSk" in win_cmd
    assert "Start-Process" in win_cmd
    assert "certutil.exe -addstore -f Root" in win_ps1
    assert "Start-Process powershell.exe" in win_ps1
    assert info["cert_urls"][0] in win_cmd
    assert info["cert_urls"][0] in win_ps1
    assert "curl.exe -fsSk" in cert_scripts_module._trust_windows_powershell_body(info)
    assert info["cert_urls"][0] in cert_scripts_module.trust_linux_script(info)
    assert "Trying" in cert_scripts_module.trust_linux_script(info)
    assert info["base_url"] in cert_scripts_module.trust_macos_script(info)
