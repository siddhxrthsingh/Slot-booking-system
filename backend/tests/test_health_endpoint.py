import unittest

from fastapi.testclient import TestClient

from app.main import app


class HealthEndpointTests(unittest.TestCase):
    def setUp(self):
        # No context manager: avoids running app lifespan (DB connection).
        self.client = TestClient(app)

    def test_get_health_unchanged(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok", "version": "1.0.0"})

    def test_head_health_returns_200_without_body(self):
        resp = self.client.head("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b"")


if __name__ == "__main__":
    unittest.main()
