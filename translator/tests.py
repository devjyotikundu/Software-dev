"""
Contract test for LEM-05 (Exercise C2, Lab 4).

Given: text + source/target, no login
When: POST /translate/
Then: 200 with translated text

The actual call to Google Translate is mocked out so the test suite is fast
and doesn't depend on internet access in CI.
"""
import json
from unittest.mock import patch

from django.test import TestCase, Client
from django.urls import reverse


class TranslateContractTest(TestCase):
    def setUp(self):
        self.client = Client()

    @patch('translator.views._do_translate', return_value='Hola')
    def test_translate_works_without_login(self, mock_translate):
        response = self.client.post(
            reverse('translator:translate'),
            data=json.dumps({'text': 'Hello', 'source': 'en', 'target': 'es'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['translated_text'], 'Hola')

    def test_empty_text_returns_400(self):
        response = self.client.post(
            reverse('translator:translate'),
            data=json.dumps({'text': '', 'source': 'en', 'target': 'es'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
