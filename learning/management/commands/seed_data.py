"""
Seeds a couple of languages with a handful of short sample lessons, so the
"Learn a language" flow has something to demo right after a fresh clone.

Usage:
    python manage.py seed_data
"""
from django.core.management.base import BaseCommand
from learning.models import Language, Lesson


LESSON_DATA = {
    'Spanish': [
        ('Greetings', 'Hola = Hello. Buenos dias = Good morning. Adios = Goodbye.'),
        ('Numbers 1-5', 'Uno, dos, tres, cuatro, cinco.'),
        ('Everyday phrases', 'Como estas? = How are you? Estoy bien = I am fine.'),
    ],
    'French': [
        ('Greetings', 'Bonjour = Hello. Bonsoir = Good evening. Au revoir = Goodbye.'),
        ('Numbers 1-5', 'Un, deux, trois, quatre, cinq.'),
        ('Everyday phrases', 'Comment ca va? = How are you? Ca va bien = I am well.'),
    ],
}


class Command(BaseCommand):
    help = 'Seed sample languages and lessons for demo purposes.'

    def handle(self, *args, **options):
        for language_name, lessons in LESSON_DATA.items():
            language, created = Language.objects.get_or_create(name=language_name)
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created language: {language_name}'))

            for order, (title, contents) in enumerate(lessons, start=1):
                lesson, created = Lesson.objects.get_or_create(
                    language=language,
                    lesson_order=order,
                    defaults={'title': title, 'contents': contents},
                )
                if created:
                    self.stdout.write(self.style.SUCCESS(f'  Added lesson {order}: {title}'))

        self.stdout.write(self.style.SUCCESS('Seeding complete.'))
