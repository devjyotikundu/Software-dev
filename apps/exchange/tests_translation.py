"""In-chat translation, romanization and the endpoints behind them."""
import json
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.ai_services.client import AIUnavailable
from apps.core.testing import make_onboarded_user, seed_reference_data
from apps.matching.services import requests as req

from . import translation
from .models import Message
from .transliteration import guess_language, romanize, script_of

AI_ON = {"PROVIDER": "anthropic", "API_KEY": "k", "MODEL": "m", "BASE_URL": "", "TIMEOUT_SECONDS": 1,
         "MAX_INPUT_CHARS": 500, "REQUESTS_PER_HOUR": 30}


class FakeClient:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, []

    def complete(self, *, system, prompt, max_tokens=400):
        self.calls.append(prompt)
        if self.error:
            raise self.error
        return self.reply


def reply(text, detected="hi", romanized=True):
    return json.dumps({"detected_language": detected, "romanized_input": romanized, "translation": text})


class TransliterationTests(SimpleTestCase):
    def test_hindi_romanization_drops_silent_vowels(self):
        cases = {
            "आप कैसे हैं?": "aap kaise hain?", "कल मिलते हैं": "kal milte hain", "करता": "kartaa",
            "समझना": "samajhnaa", "कमल": "kamal", "ज़रूर": "zaroor", "मुझे भूख लगी है": "mujhe bhookh lagee hai",
        }
        for devanagari, roman in cases.items():
            with self.subTest(devanagari):
                self.assertEqual(romanize(devanagari), roman)

    def test_bengali_romanization(self):
        self.assertEqual(romanize("আমি তোমাকে ভালোবাসি"), "aami tomaake bhaalobaasi")
        self.assertEqual(romanize("জল"), "jol")

    def test_latin_text_passes_through(self):
        self.assertEqual(romanize("Hello 123!"), "Hello 123!")

    def test_scripts_and_roman_hindi_detection(self):
        self.assertEqual(script_of("आप"), "devanagari")
        self.assertEqual(script_of("আমি"), "bengali")
        cases = {
            "tum kaha ja rahe ho": "hi-Latn", "mujhe hindi thodi thodi aati hai": "hi-Latn",
            "kal milte hain": "hi-Latn", "Aap kaise ho?": "hi-Latn", "ami tomake bhalobashi": "bn-Latn",
            "Where are you going?": "en", "I am hungry": "en", "आप कैसे हैं?": "hi",
        }
        for text, expected in cases.items():
            with self.subTest(text):
                self.assertEqual(guess_language(text), expected)


class TranslateRuleTests(TestCase):
    """The translation function with a fake AI client."""

    @classmethod
    def setUpTestData(cls):
        seed_reference_data()
        asha = make_onboarded_user("asha", native="bn", learning="en")
        tom = make_onboarded_user("tom", native="en", learning="bn")
        cls.room = req.accept_request(req.send_request(asha, tom).request, tom).room
        cls.asha = asha

    def setUp(self):
        cache.clear()

    def message(self, body):
        return Message.objects.create(room=self.room, sender=self.asha, body=body)

    def test_roman_hindi_is_translated_as_hindi(self):
        client = FakeClient(reply("Where are you going?"))
        result = translation.translate_message(self.message("tum kaha ja rahe ho"), target="en", client=client)
        self.assertEqual((result.translation, result.detected_language, result.romanized_input),
                         ("Where are you going?", "hi", True))
        self.assertIn("NOT English", client.calls[0])
        self.assertIn("<text>tum kaha ja rahe ho</text>", client.calls[0])

    def test_english_to_devanagari_with_learning_extras(self):
        client = FakeClient(reply("मुझे भूख लगी है", detected="en", romanized=False))
        result = translation.translate_message(self.message("I'm hungry."), target="hi", client=client)
        self.assertEqual(result.translation, "मुझे भूख लगी है")
        self.assertEqual(result.translation_romanized, "mujhe bhookh lagee hai")
        self.assertEqual(result.locale, "hi-IN")
        self.assertIn("Devanagari", client.calls[0])

    def test_roman_output_requested_but_devanagari_returned_is_converted_offline(self):
        client = FakeClient(reply("मुझे भूख लगी है", detected="en"))
        result = translation.translate_message(self.message("I'm hungry."), target="hi", fmt="roman", client=client)
        self.assertEqual(result.translation, "mujhe bhookh lagee hai")
        self.assertIn("Latin letters", client.calls[0])

    def test_original_in_devanagari_gets_romanized_for_learning(self):
        client = FakeClient(reply("I'm hungry.", detected="hi", romanized=False))
        result = translation.translate_message(self.message("मुझे भूख लगी है"), target="en", client=client)
        self.assertEqual(result.original_romanized, "mujhe bhookh lagee hai")

    def test_wrong_script_or_bad_reply_is_unavailable(self):
        cases = [
            ("hi", "native", reply("I'm hungry")),            # asked for Devanagari, got English
            ("en", "native", reply("मुझे भूख लगी है")),       # asked for English, got Devanagari
            ("en", "native", "Sorry, I can't help."),        # not JSON
            ("en", "native", json.dumps({"translation": ""})),
        ]
        for target, fmt, bad in cases:
            with self.subTest(bad=bad[:30]), self.assertRaisesMessage(translation.TranslationError, translation.UNAVAILABLE):
                translation.translate_message(self.message(f"text {bad[:5]}"), target=target, fmt=fmt,
                                              client=FakeClient(bad))
        with self.assertRaisesMessage(translation.TranslationError, translation.UNAVAILABLE):
            translation.translate_message(self.message("hi"), target="en", client=FakeClient(error=AIUnavailable()))

    def test_results_are_cached_not_stored(self):
        message = self.message("kal milte hain")
        client = FakeClient(reply("See you tomorrow."))
        translation.translate_message(message, target="en", client=client)
        translation.translate_message(message, target="en", client=client)
        self.assertEqual(len(client.calls), 1)
        message.refresh_from_db()
        self.assertEqual(message.body, "kal milte hain")   # the original is never changed


class EndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_reference_data()

    def setUp(self):
        cache.clear()
        self.asha = make_onboarded_user("asha", native="bn", learning="en")
        self.tom = make_onboarded_user("tom", native="en", learning="bn")
        self.room = req.accept_request(req.send_request(self.asha, self.tom).request, self.tom).room
        self.msg = Message.objects.create(room=self.room, sender=self.asha, body="আমি তোমাকে ভালোবাসি")
        self.client.force_login(self.tom)

    def url(self, action, message=None):
        return reverse(f"exchange:{action}_message", kwargs={"room_id": self.room.pk, "message_id": (message or self.msg).pk})

    def test_romanize_works_without_ai(self):
        response = self.client.post(self.url("romanize"))
        self.assertEqual(response.json(), {"ok": True, "romanized": "aami tomaake bhaalobaasi",
                                           "script": "bengali", "language": "bn"})

    def test_romanize_rejects_latin_text(self):
        latin = Message.objects.create(room=self.room, sender=self.asha, body="hello")
        self.assertEqual(self.client.post(self.url("romanize", latin)).status_code, 400)

    def test_translate_without_ai_is_unavailable_but_harmless(self):
        response = self.client.post(self.url("translate"), {"target": "en"})
        self.assertEqual((response.status_code, response.json()["error"]), (503, "Translation unavailable. Try again."))

    @override_settings(AI=AI_ON)
    def test_translate_with_ai(self):
        with mock.patch("apps.exchange.translation.get_client", return_value=FakeClient(reply("I love you.", detected="bn", romanized=False))):
            data = self.client.post(self.url("translate"), {"target": "en"}).json()
        self.assertEqual((data["ok"], data["translation"], data["target_name"]), (True, "I love you.", "English"))
        self.assertEqual(data["original_romanized"], "aami tomaake bhaalobaasi")

    @override_settings(AI=AI_ON)
    def test_only_the_exchange_languages_can_be_targets(self):
        self.assertEqual(self.client.post(self.url("translate"), {"target": "hi"}).status_code, 400)

    def test_outsiders_other_rooms_and_get_requests(self):
        self.assertEqual(self.client.get(self.url("romanize")).status_code, 405)
        eve = make_onboarded_user("eve", native="hi", learning="en")
        self.client.force_login(eve)
        self.assertEqual(self.client.post(self.url("romanize")).status_code, 404)
        self.client.force_login(self.tom)
        sam = make_onboarded_user("sam", native="bn", learning="en")
        other_room = req.accept_request(req.send_request(sam, self.tom).request, self.tom).room
        foreign = Message.objects.create(room=other_room, sender=sam, body="আমি")
        wrong = reverse("exchange:romanize_message", kwargs={"room_id": self.room.pk, "message_id": foreign.pk})
        self.assertEqual(self.client.post(wrong).status_code, 404)

    @override_settings(RATE_LIMITS={"translate": (2, 3600)})
    def test_rate_limit(self):
        self.client.post(self.url("romanize")); self.client.post(self.url("romanize"))
        self.assertEqual(self.client.post(self.url("romanize")).status_code, 429)

    def test_nothing_is_written_to_the_database(self):
        before = Message.objects.count()
        self.client.post(self.url("romanize"))
        self.assertEqual(Message.objects.count(), before)

    def test_room_page_has_the_tools_wired_up(self):
        page = self.client.get(reverse("exchange:room", kwargs={"room_id": self.room.pk}))
        self.assertContains(page, 'data-languages="bn,en"')
        self.assertContains(page, "js/translate.js")
        self.assertContains(page, "data-tr-settings")
