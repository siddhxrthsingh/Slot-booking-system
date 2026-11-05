import unittest

from app.config import get_settings
from app.services.auth_service import verify_admin_credentials, upsert_admin


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


class AdminMultiLoginTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        get_settings.cache_clear()

    def tearDown(self):
        get_settings.cache_clear()

    async def test_emp001_authenticates_as_admin(self):
        profile = await verify_admin_credentials("EMP001", "admin123")
        self.assertIsNotNone(profile)
        self.assertEqual(profile["role"], "admin")
        self.assertEqual(profile["employee_id"], "EMP001")

    async def test_emp002_authenticates_as_admin(self):
        profile = await verify_admin_credentials("EMP002", "admin123")
        self.assertIsNotNone(profile)
        self.assertEqual(profile["role"], "admin")
        self.assertEqual(profile["employee_id"], "EMP002")

    async def test_emp003_authenticates_as_admin(self):
        profile = await verify_admin_credentials("EMP003", "admin123")
        self.assertIsNotNone(profile)
        self.assertEqual(profile["role"], "admin")
        self.assertEqual(profile["employee_id"], "EMP003")

    async def test_unknown_employee_id_is_rejected(self):
        profile = await verify_admin_credentials("EMP999", "admin123")
        self.assertIsNone(profile)

    async def test_wrong_password_is_rejected_for_new_admins(self):
        profile = await verify_admin_credentials("EMP002", "wrong-password")
        self.assertIsNone(profile)

    async def test_each_admin_gets_independent_upserted_document_with_admin_role(self):
        db = FakeDb()
        for eid in ("EMP001", "EMP002", "EMP003"):
            profile = await verify_admin_credentials(eid, "admin123")
            user_doc = await upsert_admin(db, profile)
            self.assertEqual(user_doc["role"], "admin")
            self.assertEqual(user_doc["srn"], eid)

        self.assertEqual(len(db["users"].docs), 3)

    async def test_upsert_admin_is_idempotent(self):
        db = FakeDb()
        profile = await verify_admin_credentials("EMP002", "admin123")
        await upsert_admin(db, profile)
        await upsert_admin(db, profile)  # running setup again must not duplicate

        matching = [d for d in db["users"].docs if d["srn"] == "EMP002"]
        self.assertEqual(len(matching), 1)


if __name__ == "__main__":
    unittest.main()
