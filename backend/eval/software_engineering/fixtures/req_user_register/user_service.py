from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class User:
    username: str
    email: str


_USERS: dict[str, User] = {}


def reset_users() -> None:
    _USERS.clear()


def register_user(username: str, email: str, password: str) -> dict[str, object]:
    """
    Expected behavior:
    - username must be non-empty
    - email must contain '@'
    - password length must be >= 8
    - duplicate username should return ok=False
    """
    # TODO: implement full validation + duplicate handling
    if not username:
        return {"ok": False, "error": "username_required"}
    _USERS[username] = User(username=username, email=email)
    return {"ok": True, "user": {"username": username, "email": email}}

