"""Admin router route ordering tests."""

from app.admin.router import router


def test_broadcast_email_route_before_user_id_route():
    post_paths = [route.path for route in router.routes if hasattr(route, "methods") and "POST" in route.methods]
    broadcast_idx = post_paths.index("/users/broadcast-email")
    user_update_idx = post_paths.index("/users/{user_id}")
    assert broadcast_idx < user_update_idx
