import unittest
from datetime import datetime, timezone

from app.services.auth_service import upsert_user


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
