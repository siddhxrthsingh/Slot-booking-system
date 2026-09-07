import unittest

from app.services.admin_service import list_facilities


class FakeCursor:
    def __init__(self, docs):
        self.docs = list(docs)

    def sort(self, key_or_list, direction=None):
        if isinstance(key_or_list, str):
            reverse = (direction if direction is not None else 1) < 0
            self.docs.sort(key=lambda d: d.get(key_or_list), reverse=reverse)
        else:
            for key, dir_ in reversed(key_or_list):
                self.docs.sort(key=lambda d: d.get(key), reverse=dir_ < 0)
        return self

    async def to_list(self, length):
        return self.docs[:length]


class FakeCollection:
    def __init__(self, docs):
        self.docs = list(docs)

    def find(self, query=None):
        query = query or {}
        return FakeCursor([d for d in self.docs if all(d.get(k) == v for k, v in query.items())])


class FakeDb:
    def __init__(self, facilities):
        self.collections = {"facilities": FakeCollection(facilities)}

    def __getitem__(self, name):
        return self.collections[name]


def facility(**overrides):
    base = {
        "_id": "fac-1",
        "campus": "RR",
        "sport": "Badminton",
        "facility_type": "court",
        "name": "Court 1",
        "display_name": "Badminton Court 1",
        "capacity": 6,
        "is_active": True,
        "sort_order": 1,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": None,
    }
    base.update(overrides)
    return base


class ListFacilitiesTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_only_requested_fields_with_id_conversion(self):
        db = FakeDb([facility()])

        result = await list_facilities(db, campus="RR")

        self.assertEqual(len(result), 1)
        entry = result[0]
        self.assertEqual(
            set(entry.keys()),
            {"id", "campus", "sport", "facility_type", "name", "display_name",
             "capacity", "is_active", "sort_order"},
        )
        self.assertEqual(entry["id"], "fac-1")
        self.assertNotIn("_id", entry)
        self.assertNotIn("created_at", entry)
        self.assertNotIn("updated_at", entry)

    async def test_inactive_facilities_are_not_filtered_out(self):
        db = FakeDb([
            facility(_id="active-1", name="Court 1", is_active=True, sort_order=1),
            facility(_id="inactive-1", name="Court 2", is_active=False, sort_order=2),
        ])

        result = await list_facilities(db, campus="RR")

        self.assertEqual(len(result), 2)
        self.assertTrue(any(f["is_active"] is False for f in result))

    async def test_sorted_by_sort_order_then_name(self):
        db = FakeDb([
            facility(_id="c2", name="Court 2", sort_order=2),
            facility(_id="c1", name="Court 1", sort_order=1),
            facility(_id="c1b", name="Court 1", sport="Squash", sort_order=1),
        ])

        result = await list_facilities(db, campus="RR")

        # sort_order 1 entries first (name tiebreak keeps "Court 1" grouped),
        # sort_order 2 last.
        self.assertEqual([f["id"] for f in result], ["c1", "c1b", "c2"])

    async def test_only_requested_campus_is_returned(self):
        db = FakeDb([
            facility(_id="rr-1", campus="RR"),
            facility(_id="ec-1", campus="EC"),
        ])

        result = await list_facilities(db, campus="RR")

        self.assertEqual([f["id"] for f in result], ["rr-1"])

    async def test_defaults_to_rr_campus(self):
        db = FakeDb([facility(_id="rr-1", campus="RR")])

        result = await list_facilities(db)

        self.assertEqual([f["id"] for f in result], ["rr-1"])


if __name__ == "__main__":
    unittest.main()
