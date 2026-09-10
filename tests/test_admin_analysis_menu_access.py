import unittest

from app import app


class AdminAnalysisMenuAccessTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def _access(self, **session_values):
        with self.client.session_transaction() as sess:
            sess.clear()
            sess.update(session_values)
        response = self.client.get("/api/admin/menu-access")
        self.assertEqual(response.status_code, 200)
        return response.get_json()["is_admin"]

    def test_hidden_without_admin_session(self):
        self.assertFalse(self._access())

    def test_visible_for_admin_only_session(self):
        self.assertTrue(self._access(admin=True, admin_user_id=1))

    def test_hidden_when_general_member_session_is_also_active(self):
        self.assertFalse(self._access(admin=True, admin_user_id=1, user_id=22))

    def test_hidden_when_business_session_is_also_active(self):
        for key in ("agent_id", "operator_id", "loan_consultant_id"):
            with self.subTest(key=key):
                self.assertFalse(self._access(admin=True, admin_user_id=1, **{key: 22}))


if __name__ == "__main__":
    unittest.main()