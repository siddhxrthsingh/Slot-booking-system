"""
Focused checks for setup_db.py index definitions.

Regression covered: facilities identity (campus + sport + name) is relied on
by seed_facilities.py for idempotent upserts, but the corresponding index in
setup_db.py was missing unique=True, so duplicate facility documents could
be created (e.g. by a manual insert or a non-idempotent seed path).
"""
import asyncio
import importlib
import unittest
from unittest.mock import patch


class _FakeCollection:
    def __init__(self, name, calls):
        self.name = name
        self.calls = calls

    async def create_index(self, keys, **kwargs):
        self.calls.append((self.name, keys, kwargs))
        return "ok"


class _FakeDb:
    def __init__(self, calls):
        self.calls = calls

    def __getitem__(self, name):
        return _FakeCollection(name, self.calls)


class _FakeClient:
    def __init__(self, calls):
        self._db = _FakeDb(calls)

    def __getitem__(self, name):
        return self._db

    def close(self):
        pass


class SetupDbIndexTests(unittest.TestCase):
    def _run_main_and_collect_calls(self):
        calls = []
        with patch(
            "motor.motor_asyncio.AsyncIOMotorClient",
            return_value=_FakeClient(calls),
        ):
            setup_db = importlib.import_module("setup_db")
            importlib.reload(setup_db)
            asyncio.run(setup_db.main())
        return calls

    def test_facilities_identity_index_is_unique(self):
        calls = self._run_main_and_collect_calls()
        facility_calls = [c for c in calls if c[0] == "facilities"]
        identity_calls = [
            c for c in facility_calls
            if c[1] == [("campus", 1), ("sport", 1), ("name", 1)]
        ]
        self.assertEqual(len(identity_calls), 1)
        _, _, kwargs = identity_calls[0]
        self.assertTrue(
            kwargs.get("unique"),
            "facilities (campus, sport, name) index must be unique to match "
            "seed_facilities.py's upsert identity and prevent duplicates.",
        )

    def test_bookings_user_slot_index_is_unique(self):
        # One booking document per user per slot, ever (rejoin-after-leave is
        # blocked by product rule, not by allowing a fresh document) — must
        # stay unique.
        calls = self._run_main_and_collect_calls()
        booking_calls = [
            c for c in calls
            if c[0] == "bookings" and c[1] == [("user_id", 1), ("slot_id", 1)]
        ]
        self.assertEqual(len(booking_calls), 1)
        self.assertTrue(booking_calls[0][2].get("unique"))

    def test_generated_slot_uniqueness_excludes_manual_slots(self):
        calls = self._run_main_and_collect_calls()
        slot_identity_calls = [
            c for c in calls
            if c[0] == "slots" and c[2].get("unique")
        ]
        self.assertEqual(len(slot_identity_calls), 1)
        _, _, kwargs = slot_identity_calls[0]
        partial = kwargs.get("partialFilterExpression", {})
        self.assertEqual(partial.get("slot_type"), "generated")

    def test_main_is_idempotent_when_rerun(self):
        # create_index is idempotent in real MongoDB; verify main() can be
        # invoked twice without raising (no duplicate/conflicting definitions
        # for the same field set that would error on a real server).
        self._run_main_and_collect_calls()
        self._run_main_and_collect_calls()


if __name__ == "__main__":
    unittest.main()
