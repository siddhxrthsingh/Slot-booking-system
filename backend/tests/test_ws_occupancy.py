import asyncio
import json
import unittest
from datetime import timedelta, timezone, datetime

from bson import ObjectId

from app.dependencies import get_ws_user
from app.services.auth_service import create_access_token
from app.ws_manager import ConnectionManager


class FakeWebSocket:
    def __init__(self):
        self.accepted = False
        self.sent: list[str] = []

    async def accept(self):
        self.accepted = True

    async def send_text(self, message: str):
        self.sent.append(message)


class FakeDB:
    """Minimal fake with just what get_ws_user needs."""

    def __init__(self, user: dict | None):
        self._user = user

    def __getitem__(self, name):
        assert name == "users"
        return self

    async def find_one(self, query):
        if self._user and self._user["_id"] == query.get("_id"):
            return self._user
        return None


class TestConnectionManagerOccupancy(unittest.TestCase):
    def test_subscribe_then_broadcast_reaches_only_subscribed_slot(self):
        async def run():
            manager = ConnectionManager()
            ws_a, ws_b = FakeWebSocket(), FakeWebSocket()
            conn_a = await manager.connect_authenticated(ws_a, user_id="u1", role="student")
            conn_b = await manager.connect_authenticated(ws_b, user_id="u2", role="student")

            manager.subscribe(ws_a, ["slot-1"])
            manager.subscribe(ws_b, ["slot-2"])

            await manager.broadcast_occupancy("slot-1", {"booked_count": 3})

            self.assertEqual(len(ws_a.sent), 1)
            self.assertEqual(len(ws_b.sent), 0)
            payload = json.loads(ws_a.sent[0])
            self.assertEqual(payload["type"], "occupancy_update")
            self.assertEqual(payload["data"]["slot_id"], "slot-1")
            self.assertEqual(payload["data"]["booked_count"], 3)

        asyncio.run(run())

    def test_unsubscribe_stops_further_delivery(self):
        async def run():
            manager = ConnectionManager()
            ws = FakeWebSocket()
            await manager.connect_authenticated(ws, user_id="u1", role="student")
            manager.subscribe(ws, ["slot-1"])
            manager.unsubscribe(ws, ["slot-1"])

            await manager.broadcast_occupancy("slot-1", {"booked_count": 1})

            self.assertEqual(len(ws.sent), 0)

        asyncio.run(run())

    def test_disconnect_removes_connection_and_subscriptions(self):
        async def run():
            manager = ConnectionManager()
            ws = FakeWebSocket()
            await manager.connect_authenticated(ws, user_id="u1", role="student")
            manager.subscribe(ws, ["slot-1"])
            manager.disconnect(ws)

            await manager.broadcast_occupancy("slot-1", {"booked_count": 1})

            self.assertEqual(len(ws.sent), 0)
            self.assertNotIn(ws, manager.active)

        asyncio.run(run())


class TestWsAuth(unittest.TestCase):
    def test_valid_token_resolves_user(self):
        async def run():
            user_id = str(ObjectId())
            token = create_access_token(user_id, "student")
            db = FakeDB({"_id": ObjectId(user_id), "role": "student"})

            user = await get_ws_user(token, db)

            self.assertIsNotNone(user)
            self.assertEqual(user["id"], user_id)

        asyncio.run(run())

    def test_invalid_token_rejected(self):
        async def run():
            db = FakeDB(None)
            user = await get_ws_user("not-a-real-token", db)
            self.assertIsNone(user)

        asyncio.run(run())

    def test_token_for_unknown_user_rejected(self):
        async def run():
            token = create_access_token(str(ObjectId()), "student")
            db = FakeDB(None)  # user lookup misses
            user = await get_ws_user(token, db)
            self.assertIsNone(user)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
