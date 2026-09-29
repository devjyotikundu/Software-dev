"""
Seeds several languages with ordered lessons, each lesson carrying its own
vocabulary pairs and a short quiz, so the "Learn a language" flow has
plenty of real content right after a fresh clone.

Safe to re-run: existing languages/lessons/vocab/quiz are updated in place
rather than duplicated.

Usage:
    python manage.py seed_data
"""
from django.core.management.base import BaseCommand
from learning.models import Language, Lesson, VocabularyItem, QuizQuestion


# Lesson topics, in order, shared across every language so the course
# structure is consistent no matter which language a learner picks.
LESSON_TITLES = [
    'Greetings',
    'Numbers 1-5',
    'Everyday phrases',
    'Family',
    'Colors',
]

# One short intro sentence per topic, shown at the top of the lesson.
LESSON_INTROS = [
    'Learn how to say hello, greet people at different times of day, and say goodbye.',
    'Learn to count from one to five.',
    'Handy phrases for everyday conversation.',
    'Words for talking about your family.',
    'Common colors you will use all the time.',
]

# vocab[language][lesson_index] = list of (term, translation) pairs.
VOCAB = {
    'Spanish': [
        [('Hola', 'Hello'), ('Buenos dias', 'Good morning'), ('Buenas noches', 'Good evening'),
         ('Adios', 'Goodbye'), ('Gracias', 'Thank you')],
        [('Uno', 'One'), ('Dos', 'Two'), ('Tres', 'Three'), ('Cuatro', 'Four'), ('Cinco', 'Five')],
        [('Como estas?', 'How are you?'), ('Estoy bien', 'I am fine'), ('Por favor', 'Please'),
         ('Perdon', 'Excuse me'), ('Si / No', 'Yes / No')],
        [('Madre', 'Mother'), ('Padre', 'Father'), ('Hermana', 'Sister'),
         ('Hermano', 'Brother'), ('Familia', 'Family')],
        [('Rojo', 'Red'), ('Azul', 'Blue'), ('Verde', 'Green'), ('Amarillo', 'Yellow'), ('Negro', 'Black')],
    ],
    'French': [
        [('Bonjour', 'Hello'), ('Bonjour', 'Good morning'), ('Bonsoir', 'Good evening'),
         ('Au revoir', 'Goodbye'), ('Merci', 'Thank you')],
        [('Un', 'One'), ('Deux', 'Two'), ('Trois', 'Three'), ('Quatre', 'Four'), ('Cinq', 'Five')],
        [('Comment ca va?', 'How are you?'), ('Ca va bien', 'I am fine'), ('S\'il vous plait', 'Please'),
         ('Excusez-moi', 'Excuse me'), ('Oui / Non', 'Yes / No')],
        [('Mere', 'Mother'), ('Pere', 'Father'), ('Soeur', 'Sister'),
         ('Frere', 'Brother'), ('Famille', 'Family')],
        [('Rouge', 'Red'), ('Bleu', 'Blue'), ('Vert', 'Green'), ('Jaune', 'Yellow'), ('Noir', 'Black')],
    ],
    'German': [
        [('Hallo', 'Hello'), ('Guten Morgen', 'Good morning'), ('Guten Abend', 'Good evening'),
         ('Auf Wiedersehen', 'Goodbye'), ('Danke', 'Thank you')],
        [('Eins', 'One'), ('Zwei', 'Two'), ('Drei', 'Three'), ('Vier', 'Four'), ('Fuenf', 'Five')],
        [('Wie geht\'s?', 'How are you?'), ('Mir geht es gut', 'I am fine'), ('Bitte', 'Please'),
         ('Entschuldigung', 'Excuse me'), ('Ja / Nein', 'Yes / No')],
        [('Mutter', 'Mother'), ('Vater', 'Father'), ('Schwester', 'Sister'),
         ('Bruder', 'Brother'), ('Familie', 'Family')],
        [('Rot', 'Red'), ('Blau', 'Blue'), ('Gruen', 'Green'), ('Gelb', 'Yellow'), ('Schwarz', 'Black')],
    ],
    'Italian': [
        [('Ciao', 'Hello'), ('Buongiorno', 'Good morning'), ('Buonasera', 'Good evening'),
         ('Arrivederci', 'Goodbye'), ('Grazie', 'Thank you')],
        [('Uno', 'One'), ('Due', 'Two'), ('Tre', 'Three'), ('Quattro', 'Four'), ('Cinque', 'Five')],
        [('Come stai?', 'How are you?'), ('Sto bene', 'I am fine'), ('Per favore', 'Please'),
         ('Mi scusi', 'Excuse me'), ('Si / No', 'Yes / No')],
        [('Madre', 'Mother'), ('Padre', 'Father'), ('Sorella', 'Sister'),
         ('Fratello', 'Brother'), ('Famiglia', 'Family')],
        [('Rosso', 'Red'), ('Blu', 'Blue'), ('Verde', 'Green'), ('Giallo', 'Yellow'), ('Nero', 'Black')],
    ],
    'Portuguese': [
        [('Ola', 'Hello'), ('Bom dia', 'Good morning'), ('Boa noite', 'Good evening'),
         ('Adeus', 'Goodbye'), ('Obrigado', 'Thank you')],
        [('Um', 'One'), ('Dois', 'Two'), ('Tres', 'Three'), ('Quatro', 'Four'), ('Cinco', 'Five')],
        [('Como voce esta?', 'How are you?'), ('Estou bem', 'I am fine'), ('Por favor', 'Please'),
         ('Com licenca', 'Excuse me'), ('Sim / Nao', 'Yes / No')],
        [('Mae', 'Mother'), ('Pai', 'Father'), ('Irma', 'Sister'),
         ('Irmao', 'Brother'), ('Familia', 'Family')],
        [('Vermelho', 'Red'), ('Azul', 'Blue'), ('Verde', 'Green'), ('Amarelo', 'Yellow'), ('Preto', 'Black')],
    ],
    'Japanese': [
        [('Konnichiwa', 'Hello'), ('Ohayou gozaimasu', 'Good morning'), ('Konbanwa', 'Good evening'),
         ('Sayounara', 'Goodbye'), ('Arigatou', 'Thank you')],
        [('Ichi', 'One'), ('Ni', 'Two'), ('San', 'Three'), ('Yon', 'Four'), ('Go', 'Five')],
        [('Ogenki desu ka?', 'How are you?'), ('Genki desu', 'I am fine'), ('Onegaishimasu', 'Please'),
         ('Sumimasen', 'Excuse me'), ('Hai / Iie', 'Yes / No')],
        [('Haha', 'Mother'), ('Chichi', 'Father'), ('Ane', 'Older sister'),
         ('Ani', 'Older brother'), ('Kazoku', 'Family')],
        [('Aka', 'Red'), ('Ao', 'Blue'), ('Midori', 'Green'), ('Kiiro', 'Yellow'), ('Kuro', 'Black')],
    ],
}


def _build_quiz(language_name, vocab_pairs):
    """
    Auto-generate 3 short quiz questions from a lesson's vocab pairs, so
    every lesson gets a quiz without hand-writing one for every language.
    Mixes both directions (term -> meaning and meaning -> term).
    """
    quiz = []
    for i, (term, translation) in enumerate(vocab_pairs[:3]):
        if i % 2 == 0:
            quiz.append((f"How do you say '{translation}' in {language_name}?", term))
        else:
            quiz.append((f"What does '{term}' mean in English?", translation))
    return quiz


class Command(BaseCommand):
    help = 'Seed languages, lessons, vocabulary, and quiz questions for demo purposes.'

    def handle(self, *args, **options):
        for language_name, lessons_vocab in VOCAB.items():
            language, created = Language.objects.get_or_create(name=language_name)
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created language: {language_name}'))

            for index, vocab_pairs in enumerate(lessons_vocab):
                order = index + 1
                title = LESSON_TITLES[index]
                intro = LESSON_INTROS[index]

                lesson, _ = Lesson.objects.update_or_create(
                    language=language,
                    lesson_order=order,
                    defaults={'title': title, 'contents': intro},
                )

                for v_order, (term, translation) in enumerate(vocab_pairs, start=1):
                    VocabularyItem.objects.update_or_create(
                        lesson=lesson,
                        order=v_order,
                        defaults={'term': term, 'translation': translation},
                    )

                for q_order, (question, answer) in enumerate(_build_quiz(language_name, vocab_pairs), start=1):
                    QuizQuestion.objects.update_or_create(
                        lesson=lesson,
                        order=q_order,
                        defaults={'question': question, 'answer': answer},
                    )

                self.stdout.write(self.style.SUCCESS(
                    f'  {language_name} lesson {order} ({title}): '
                    f'{len(vocab_pairs)} vocab, {min(3, len(vocab_pairs))} quiz Qs'
                ))

        self.stdout.write(self.style.SUCCESS('Seeding complete.'))
