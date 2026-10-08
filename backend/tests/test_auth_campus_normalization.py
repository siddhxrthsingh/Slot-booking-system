import unittest
from unittest.mock import patch

from app.services import auth_service
from app.services.auth_service import normalize_campus, verify_pesu_credentials


class FakeResponse:
    status_code = 200

    def __init__(self, profile):
        self._profile = profile

    def json(self):
        return {"status": True, "profile": self._profile}


class FakeClient:
    def __init__(self, profile):
        self._profile = profile

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, *args, **kwargs):
        return FakeResponse(self._profile)


async def _login_with_campus(campus):
    profile = {"srn": "PES1UG22CS001", "name": "S", "campus": campus}
    with patch.object(auth_service.httpx, "AsyncClient", lambda **kw: FakeClient(profile)):
        return await verify_pesu_credentials("PES1UG22CS001", "pw")


class NormalizeCampusTests(unittest.TestCase):
    def test_ring_road_full_name(self):
        self.assertEqual(normalize_campus("PES University (Ring Road)"), "RR")

    def test_electronic_city_full_name(self):
        self.assertEqual(normalize_campus("PES University (Electronic City)"), "EC")

    def test_canonical_codes_unchanged(self):
        self.assertEqual(normalize_campus("RR"), "RR")
        self.assertEqual(normalize_campus("EC"), "EC")

    def test_missing_campus_is_none(self):
        self.assertIsNone(normalize_campus(None))
        self.assertIsNone(normalize_campus("  "))

    def test_unknown_campus_raises(self):
        with self.assertRaises(ValueError):
            normalize_campus("Some Other Campus")


class VerifyPesuCredentialsCampusTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_name_normalized_in_profile(self):
        profile = await _login_with_campus("PES University (Ring Road)")
        self.assertEqual(profile["campus"], "RR")

    async def test_canonical_ec_preserved(self):
        profile = await _login_with_campus("EC")
        self.assertEqual(profile["campus"], "EC")

    async def test_unknown_campus_raises_instead_of_persisting(self):
        with self.assertRaises(ValueError):
            await _login_with_campus("Mars Campus")


if __name__ == "__main__":
    unittest.main()
