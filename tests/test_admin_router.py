"""Admin router route ordering tests."""

from app.admin.router import router


def test_mailing_broadcast_route_registered():
    post_paths = [route.path for route in router.routes if hasattr(route, "methods") and "POST" in route.methods]
    assert "/mailing/broadcast-email" in post_paths
    assert "/mailing/schedule" in post_paths
    assert "/users/broadcast-email" not in post_paths


def test_mailing_page_route_registered():
    get_paths = [route.path for route in router.routes if hasattr(route, "methods") and "GET" in route.methods]
    assert "/mailing" in get_paths
