"""Real-time behaviour through the WebSocket consumer."""
from asgiref.sync import sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser
from django.test import TransactionTestCase, override_settings

from apps.core.testing import make_onboarded_user, seed_reference_data
from apps.matching.services import safety

from .models import Message
from .routing import websocket_urlpatterns
from .services import rooms
from .tests_rooms import make_partners

APP = URLRouter(websocket_urlpatterns)


class SocketTests(TransactionTestCase):
    def setUp(self):
        seed_reference_data()
        self.asha, self.tom, self.room = make_partners()
        self.path = f"/ws/rooms/{self.room.pk}/"

    async def connect(self, user):
        communicator = WebsocketCommunicator(APP, self.path)
        communicator.scope["user"] = user
        connected, code = await communicator.connect()
        return communicator, connected, code

    async def test_message_reaches_both_partners_and_is_stored(self):
        a, ok_a, _ = await self.connect(self.asha)
        b, ok_b, _ = await self.connect(self.tom)
        self.assertTrue(ok_a and ok_b)
        await a.send_json_to({"type": "message", "body": "  Hello!  "})
        for side in (a, b):
            event = await side.receive_json_from(timeout=2)
            self.assertEqual((event["type"], event["body"], event["sender_id"]), ("message", "Hello!", self.asha.pk))
        self.assertEqual(await sync_to_async(Message.objects.count)(), 1)
        await a.disconnect(); await b.disconnect()

    async def test_outsiders_and_anonymous_are_refused(self):
        eve = await sync_to_async(make_onboarded_user)("eve", native="hi", learning="en")
        _, connected, code = await self.connect(eve)
        self.assertEqual((connected, code), (False, 4403))
        _, connected, code = await self.connect(AnonymousUser())
        self.assertEqual((connected, code), (False, 4401))

    async def test_invalid_messages_return_an_error_to_the_sender_only(self):
        a, _, _ = await self.connect(self.asha)
        b, _, _ = await self.connect(self.tom)
        for payload in ({"type": "message", "body": "   "}, {"type": "message", "body": "x" * 2001}, {"type": "nope"}):
            await a.send_json_to(payload)
            self.assertEqual((await a.receive_json_from(timeout=2))["type"], "error")
        await a.send_to(text_data="not json")
        self.assertEqual((await a.receive_json_from(timeout=2))["type"], "error")
        self.assertTrue(await b.receive_nothing(timeout=0.3))
        self.assertEqual(await sync_to_async(Message.objects.count)(), 0)
        await a.disconnect(); await b.disconnect()

    async def test_typing_goes_to_the_partner_only(self):
        a, _, _ = await self.connect(self.asha)
        b, _, _ = await self.connect(self.tom)
        await a.send_json_to({"type": "typing"})
        self.assertEqual(await b.receive_json_from(timeout=2), {"type": "typing", "user_id": self.asha.pk})
        self.assertTrue(await a.receive_nothing(timeout=0.3))
        await a.disconnect(); await b.disconnect()

    @override_settings(EXCHANGE={"RATE_LIMIT_MESSAGES": 2, "RATE_LIMIT_SECONDS": 60})
    async def test_rate_limit(self):
        a, _, _ = await self.connect(self.asha)
        for i in range(2):
            await a.send_json_to({"type": "message", "body": f"m{i}"})
            await a.receive_json_from(timeout=2)
        await a.send_json_to({"type": "message", "body": "too fast"})
        event = await a.receive_json_from(timeout=2)
        self.assertEqual(event["type"], "error")
        self.assertIn("quickly", event["error"])
        self.assertEqual(await sync_to_async(Message.objects.count)(), 2)
        await a.disconnect()

    async def test_blocking_closes_an_open_room(self):
        a, _, _ = await self.connect(self.asha)
        await sync_to_async(safety.block_user)(self.tom, self.asha)
        await a.send_json_to({"type": "message", "body": "still there?"})
        self.assertEqual((await a.receive_json_from(timeout=2))["type"], "error")
        self.assertEqual((await a.receive_output(timeout=2))["type"], "websocket.close")
        self.assertEqual(await sync_to_async(Message.objects.count)(), 0)

    async def test_session_changes_are_pushed_live(self):
        a, _, _ = await self.connect(self.asha)
        en_id = await sync_to_async(lambda: self.room.match.user_a_learning_language_id)()
        await sync_to_async(rooms.start_session)(self.tom, self.room.pk, first_language_id=en_id, minutes=10)
        event = await a.receive_json_from(timeout=2)
        self.assertEqual((event["type"], event["action"]), ("session", "started"))
        await a.disconnect()


class FullStackTests(TransactionTestCase):
    """Through config.asgi: origin check and session authentication."""

    def setUp(self):
        seed_reference_data()
        self.asha, self.tom, self.room = make_partners()

    async def test_foreign_origin_and_missing_login_are_rejected(self):
        from config.asgi import application
        path = f"/ws/rooms/{self.room.pk}/"
        evil = WebsocketCommunicator(application, path, headers=[(b"origin", b"https://evil.example")])
        connected, _ = await evil.connect()
        self.assertFalse(connected)
        anonymous = WebsocketCommunicator(application, path, headers=[(b"origin", b"http://testserver")])
        connected, code = await anonymous.connect()
        self.assertEqual((connected, code), (False, 4401))
