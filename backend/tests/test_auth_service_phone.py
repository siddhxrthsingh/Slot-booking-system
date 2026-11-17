import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.services.auth_service import upsert_user, verify_pesu_credentials


class FakeUsersCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    async def find_one_and_update(self, query, update, upsert=False, return_document=True):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                doc.update(update.get("$set", {}))
                return doc
        if upsert:
            new_doc = {}
            new_doc.update(update.get("$set", {}))
            new_doc.update(update.get("$setOnInsert", {}))
            self.docs.append(new_doc)
            return new_doc
        return None


class FakeDb:
    def __init__(self, users=None):
        self._users = FakeUsersCollection(users)

    def __getitem__(self, name):
        return self._users


class _FakeResponse:
    status_code = 200

    def __init__(self, profile):
        self._profile = profile

    def json(self):
        return {"status": True, "profile": self._profile}


def _fake_client(profile):
    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **kw):
            return _FakeResponse(profile)

    return _Client


class VerifyCredentialsPhoneMappingTests(unittest.IsolatedAsyncioTestCase):
    async def _verify(self, profile):
        with patch("app.services.auth_service.httpx.AsyncClient", _fake_client(profile)):
            return await verify_pesu_credentials("PES1UG22CS001", "pw")

    async def test_mobile_only_profile_maps_to_phone(self):
        result = await self._verify({"srn": "PES1UG22CS001", "mobile": "9876543210"})
        self.assertEqual(result["phone"], "9876543210")

    async def test_mobile_takes_precedence_over_legacy_keys(self):
        result = await self._verify(
            {"srn": "PES1UG22CS001", "mobile": "9876543210", "phone": "1111111111"}
        )
        self.assertEqual(result["phone"], "9876543210")

    async def test_legacy_phone_key_still_works_as_fallback(self):
        result = await self._verify({"srn": "PES1UG22CS001", "phone": "1111111111"})
        self.assertEqual(result["phone"], "1111111111")

    async def test_null_mobile_does_not_overwrite_existing_phone(self):
        result = await self._verify({"srn": "PES1UG22CS001", "mobile": None})
        self.assertIsNone(result["phone"])
        existing = {"srn": "PES1UG22CS001", "phone": "9999999999"}
        user = await upsert_user(FakeDb(users=[existing]), result)
        self.assertEqual(user["phone"], "9999999999")


class UpsertUserPhoneTests(unittest.IsolatedAsyncioTestCase):
    async def test_phone_is_persisted_when_profile_provides_it(self):
        db = FakeDb()
        profile = {"srn": "PES1UG22CS001", "name": "Student One", "phone": "9999999999"}

        user = await upsert_user(db, profile)

        self.assertEqual(user["phone"], "9999999999")

    async def test_missing_phone_does_not_blank_existing_value(self):
        existing = {"srn": "PES1UG22CS001", "name": "Student One", "phone": "9999999999"}
        db = FakeDb(users=[existing])
        profile = {"srn": "PES1UG22CS001", "name": "Student One"}  # no phone this login

        user = await upsert_user(db, profile)

        self.assertEqual(user["phone"], "9999999999")


if __name__ == "__main__":
    unittest.main()
