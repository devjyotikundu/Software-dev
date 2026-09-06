"""
Contract tests for LEM-01 (Exercise C2, Lab 4).

Story: LEM-01 — User table; registration/login endpoints and pages; session
authentication.

Given a valid new user, when they POST to /auth/register/, then the response
is 201, the user is created, and no password/hash is ever exposed.
"""
import json

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse


class RegisterContractTest(TestCase):
    def test_valid_registration_returns_201_and_hides_password(self):
        client = Client()
        payload = {
            'username': 'newlearner',
            'email': 'newlearner@example.com',
            'password1': 'S3cure-Passw0rd!',
            'password2': 'S3cure-Passw0rd!',
        }
        response = client.post(
            reverse('accounts:register'),
            data=json.dumps(payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(User.objects.filter(username='newlearner').exists())

        body = response.json()
        self.assertNotIn('password', body)
        self.assertNotIn('password1', body)
        self.assertNotIn('password2', body)

    def test_duplicate_email_is_rejected(self):
        User.objects.create_user(username='existing', email='dup@example.com', password='pass12345')
        client = Client()
        payload = {
            'username': 'someoneelse',
            'email': 'dup@example.com',
            'password1': 'S3cure-Passw0rd!',
            'password2': 'S3cure-Passw0rd!',
        }
        response = client.post(
            reverse('accounts:register'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)


class LoginContractTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='learner', password='pass12345')

    def test_correct_credentials_returns_200(self):
        client = Client()
        response = client.post(
            reverse('accounts:login'),
            data=json.dumps({'username': 'learner', 'password': 'pass12345'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

    def test_wrong_password_returns_401(self):
        client = Client()
        response = client.post(
            reverse('accounts:login'),
            data=json.dumps({'username': 'learner', 'password': 'wrong-password'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 401)
