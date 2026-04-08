from __future__ import annotations

import unittest

from user_service import register_user, reset_users


class UserServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_users()

    def test_register_user_success(self) -> None:
        result = register_user("alice", "alice@example.com", "passw0rd")
        self.assertTrue(result["ok"])
        self.assertEqual(result["user"]["username"], "alice")

    def test_register_user_email_validation(self) -> None:
        result = register_user("alice", "bad-email", "passw0rd")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "invalid_email")

    def test_register_user_password_validation(self) -> None:
        result = register_user("alice", "alice@example.com", "123")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "weak_password")

    def test_register_user_duplicate_username(self) -> None:
        first = register_user("alice", "alice@example.com", "passw0rd")
        second = register_user("alice", "alice2@example.com", "passw0rd")
        self.assertTrue(first["ok"])
        self.assertFalse(second["ok"])
        self.assertEqual(second["error"], "duplicate_username")


if __name__ == "__main__":
    unittest.main()

