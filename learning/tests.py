"""
Contract tests for LEM-02, LEM-03, LEM-04 (Exercise C2, Lab 4).
"""
import json
from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse

from .models import Language, Lesson, LearningProfile


class ProfileContractTest(TestCase):
    """LEM-02: POST /learning/profile/"""

    def setUp(self):
        self.language = Language.objects.create(name='Spanish')
        self.user = User.objects.create_user(username='learner', password='pass12345')
        self.client = Client()
        self.client.login(username='learner', password='pass12345')

    def test_authenticated_user_can_save_profile(self):
        response = self.client.post(
            reverse('learning:profile_setup'),
            data=json.dumps({'language': self.language.id, 'proficiency': 'beginner'}),
            content_type='application/json',
        )
        self.assertIn(response.status_code, (200, 201))
        body = response.json()
        self.assertEqual(body['language_id'], self.language.id)
        self.assertEqual(body['proficiency'], 'beginner')

    def test_unauthenticated_user_is_rejected(self):
        self.client.logout()
        response = self.client.post(
            reverse('learning:profile_setup'),
            data=json.dumps({'language': self.language.id, 'proficiency': 'beginner'}),
            content_type='application/json',
        )
        # login_required redirects anonymous browser requests to the login page
        self.assertEqual(response.status_code, 302)


class NextLessonContractTest(TestCase):
    """LEM-03: GET /learning/next-lesson/"""

    def setUp(self):
        self.language = Language.objects.create(name='French')
        self.lesson1 = Lesson.objects.create(
            language=self.language, lesson_order=1, title='Greetings', contents='Bonjour!'
        )
        Lesson.objects.create(
            language=self.language, lesson_order=2, title='Numbers', contents='Un, deux, trois'
        )
        self.user = User.objects.create_user(username='learner2', password='pass12345')
        LearningProfile.objects.create(user=self.user, language=self.language, proficiency='beginner')
        self.client = Client()
        self.client.login(username='learner2', password='pass12345')

    def test_returns_first_incomplete_lesson(self):
        response = self.client.get(
            reverse('learning:next_lesson'), HTTP_ACCEPT='application/json',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['lesson_id'], self.lesson1.id)
        self.assertEqual(body['lesson_order'], 1)


class ProgressContractTest(TestCase):
    """LEM-04: POST /learning/progress/"""

    def setUp(self):
        self.language = Language.objects.create(name='German')
        self.lesson = Lesson.objects.create(
            language=self.language, lesson_order=1, title='Basics', contents='Hallo!'
        )
        self.user = User.objects.create_user(username='learner3', password='pass12345')
        LearningProfile.objects.create(user=self.user, language=self.language, proficiency='beginner')
        self.client = Client()
        self.client.login(username='learner3', password='pass12345')

    def test_marking_lesson_complete_saves_progress_and_timestamp(self):
        response = self.client.post(
            reverse('learning:mark_progress'),
            data=json.dumps({'lesson_id': self.lesson.id}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['completed'])
        self.assertIsNotNone(body['completed_at'])
