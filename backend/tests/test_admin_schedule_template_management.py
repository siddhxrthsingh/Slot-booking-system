import unittest

from bson import ObjectId

from app.services.admin_service import (
    create_schedule_template,
    update_schedule_template,
    delete_schedule_template,
    list_schedule_templates,
)
from app.schemas.schedule_template import ScheduleTemplateCreate, ScheduleTemplateUpdate
from app.routers import admin as admin_router


# ---------------------------------------------------------------------------
# Minimal fake db supporting find_one/insert_one/find_one_and_update/delete_one
# ---------------------------------------------------------------------------

class _FakeCollection:
    def __init__(self, docs):
        self.docs = list(docs)

    async def find_one(self, query):
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                return d
        return None

    async def insert_one(self, doc):
        doc = dict(doc)
        doc["_id"] = ObjectId()
        self.docs.append(doc)
        return type("Result", (), {"inserted_id": doc["_id"]})()

    async def find_one_and_update(self, query, update, return_document=True):
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                for op, fields in update.items():
                    if op == "$set":
                        d.update(fields)
                return d
        return None

    async def delete_one(self, query):
        for i, d in enumerate(self.docs):
            if all(d.get(k) == v for k, v in query.items()):
                del self.docs[i]
                return type("Result", (), {"deleted_count": 1})()
        return type("Result", (), {"deleted_count": 0})()

    def find(self, query):
        matched = [d for d in self.docs if all(d.get(k) == v for k, v in query.items())]
        return _FakeCursor(matched)


class _FakeCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *args, **kwargs):
        return self

    async def to_list(self, length=None):
        return self.docs


class _FakeDb:
    def __init__(self, templates=None, facilities=None):
        self.collections = {
            "schedule_templates": _FakeCollection(templates or []),
            "facilities": _FakeCollection(facilities or []),
        }

    def __getitem__(self, name):
        return self.collections[name]


def make_facility(**overrides):
    base = {
        "_id": ObjectId(),
        "campus": "RR",
        "sport": "Badminton",
        "display_name": "Badminton Court 1",
        "capacity": 6,
        "is_active": True,
    }
    base.update(overrides)
    return base


def sport_level_payload(**overrides):
    base = {
        "campus": "RR",
        "sport": "Badminton",
        "facility_scope": "sport",
        "day_type": "weekday",
        "periods": [
            {"start_time": "06:00", "end_time": "07:00", "period_type": "staff", "is_bookable": False},
            {"start_time": "09:00", "end_time": "10:00", "period_type": "student", "is_bookable": True},
        ],
    }
    base.update(overrides)
    return base


class ScheduleTemplateSchemaValidationTests(unittest.TestCase):
    def test_valid_create_payload_passes(self):
        ScheduleTemplateCreate(**sport_level_payload())

    def test_overlapping_periods_rejected(self):
        payload = sport_level_payload(periods=[
            {"start_time": "09:00", "end_time": "10:00", "period_type": "student", "is_bookable": True},
            {"start_time": "09:30", "end_time": "10:30", "period_type": "student", "is_bookable": True},
        ])
        with self.assertRaises(Exception):
            ScheduleTemplateCreate(**payload)

    def test_end_before_start_within_period_rejected(self):
        payload = sport_level_payload(periods=[
            {"start_time": "10:00", "end_time": "09:00", "period_type": "student", "is_bookable": True},
        ])
        with self.assertRaises(Exception):
            ScheduleTemplateCreate(**payload)

    def test_facility_scope_requires_facility_id(self):
        payload = sport_level_payload(facility_scope="facility")
        with self.assertRaises(Exception):
            ScheduleTemplateCreate(**payload)

    def test_update_schema_overlap_validation(self):
        with self.assertRaises(Exception):
            ScheduleTemplateUpdate(periods=[
                {"start_time": "09:00", "end_time": "10:00", "period_type": "student", "is_bookable": True},
                {"start_time": "09:30", "end_time": "10:30", "period_type": "student", "is_bookable": True},
            ])

    def test_update_schema_allows_partial_fields(self):
        upd = ScheduleTemplateUpdate(is_active=False)
        self.assertEqual(upd.model_dump(exclude_unset=True), {"is_active": False})


class ScheduleTemplateCrudTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_sport_level_template(self):
        db = _FakeDb()
        payload = ScheduleTemplateCreate(**sport_level_payload()).model_dump()

        created = await create_schedule_template(db, payload, str(ObjectId()))

        self.assertEqual(created["sport"], "Badminton")
        self.assertIsNone(created["facility_id"])
        self.assertTrue(created["is_active"])
        self.assertEqual(len(db.collections["schedule_templates"].docs), 1)

    async def test_create_facility_scoped_template_resolves_facility(self):
        facility = make_facility()
        db = _FakeDb(facilities=[facility])
        payload = ScheduleTemplateCreate(**sport_level_payload(
            facility_scope="facility", facility_id=str(facility["_id"]),
        )).model_dump()

        created = await create_schedule_template(db, payload, str(ObjectId()))

        self.assertEqual(created["facility_id"], str(facility["_id"]))
        self.assertEqual(created["facility_name"], "Badminton Court 1")

    async def test_create_facility_scoped_template_missing_facility_raises(self):
        db = _FakeDb()
        payload = ScheduleTemplateCreate(**sport_level_payload(
            facility_scope="facility", facility_id=str(ObjectId()),
        )).model_dump()

        with self.assertRaises(LookupError):
            await create_schedule_template(db, payload, str(ObjectId()))

    async def test_update_template_fields(self):
        db = _FakeDb()
        created = await create_schedule_template(
            db, ScheduleTemplateCreate(**sport_level_payload()).model_dump(), str(ObjectId())
        )

        updated = await update_schedule_template(db, created["id"], {"priority": 5, "notes": "bumped"})

        self.assertEqual(updated["priority"], 5)
        self.assertEqual(updated["notes"], "bumped")
        self.assertIsNotNone(updated["updated_at"])

    async def test_deactivate_and_reactivate_template(self):
        db = _FakeDb()
        created = await create_schedule_template(
            db, ScheduleTemplateCreate(**sport_level_payload()).model_dump(), str(ObjectId())
        )

        deactivated = await update_schedule_template(db, created["id"], {"is_active": False})
        self.assertFalse(deactivated["is_active"])

        reactivated = await update_schedule_template(db, created["id"], {"is_active": True})
        self.assertTrue(reactivated["is_active"])

    async def test_update_missing_template_raises(self):
        db = _FakeDb()
        with self.assertRaises(LookupError):
            await update_schedule_template(db, str(ObjectId()), {"priority": 1})

    async def test_update_to_facility_scope_resolves_new_facility(self):
        facility = make_facility()
        db = _FakeDb(facilities=[facility])
        created = await create_schedule_template(
            db, ScheduleTemplateCreate(**sport_level_payload()).model_dump(), str(ObjectId())
        )

        updated = await update_schedule_template(db, created["id"], {
            "facility_scope": "facility",
            "facility_id": str(facility["_id"]),
        })

        self.assertEqual(updated["facility_id"], str(facility["_id"]))
        self.assertEqual(updated["facility_name"], "Badminton Court 1")

    async def test_delete_template(self):
        db = _FakeDb()
        created = await create_schedule_template(
            db, ScheduleTemplateCreate(**sport_level_payload()).model_dump(), str(ObjectId())
        )

        await delete_schedule_template(db, created["id"])

        self.assertEqual(len(db.collections["schedule_templates"].docs), 0)

    async def test_delete_missing_template_raises(self):
        db = _FakeDb()
        with self.assertRaises(LookupError):
            await delete_schedule_template(db, str(ObjectId()))

    async def test_list_schedule_templates_returns_json_serializable_ids(self):
        """Regression test: list_schedule_templates previously returned raw
        ObjectId values for facility_id/created_by, which FastAPI's
        jsonable_encoder cannot serialize — this crashed GET
        /admin/schedule-templates with a 500, which is what broke the admin
        dashboard's Promise.all(...) data load."""
        facility = make_facility()
        db = _FakeDb(facilities=[facility])
        admin_id = str(ObjectId())
        await create_schedule_template(
            db,
            ScheduleTemplateCreate(**sport_level_payload(
                facility_scope="facility", facility_id=str(facility["_id"]),
            )).model_dump(),
            admin_id,
        )

        templates = await list_schedule_templates(db, "RR")

        self.assertEqual(len(templates), 1)
        self.assertIsInstance(templates[0]["facility_id"], str)
        self.assertIsInstance(templates[0]["created_by"], str)
        self.assertEqual(templates[0]["facility_id"], str(facility["_id"]))
        self.assertEqual(templates[0]["created_by"], admin_id)


class ScheduleTemplateRouterAuthTests(unittest.TestCase):
    """The schedule-template management endpoints must be behind the same
    admin-only dependency as the rest of /admin — checked statically against
    the route's dependant, matching this project's existing test style
    (no HTTP-level TestClient harness is used elsewhere in this suite)."""

    def _dependant_names(self, path, method):
        for route in admin_router.router.routes:
            if route.path == path and method in route.methods:
                return {d.call.__name__ for d in route.dependant.dependencies}
        raise AssertionError(f"Route {method} {path} not found")

    def test_create_route_requires_admin(self):
        self.assertIn("require_admin", self._dependant_names("/admin/schedule-templates", "POST"))

    def test_update_route_requires_admin(self):
        self.assertIn(
            "require_admin",
            self._dependant_names("/admin/schedule-templates/{template_id}", "PATCH"),
        )

    def test_delete_route_requires_admin(self):
        self.assertIn(
            "require_admin",
            self._dependant_names("/admin/schedule-templates/{template_id}", "DELETE"),
        )


if __name__ == "__main__":
    unittest.main()
