from django.contrib.auth.models import User
from django.db import models


class Language(models.Model):
    """LanguageID (PK), LanguageName (NN, unique) — from the ER diagram."""
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Lesson(models.Model):
    """
    Lesson: LessonID (PK), LanguageID (FK), LessonOrder, Title, Contents.
    One row per lesson, ordered within its language.
    """
    language = models.ForeignKey(Language, on_delete=models.CASCADE, related_name='lessons')
    lesson_order = models.PositiveIntegerField()
    title = models.CharField(max_length=150)
    contents = models.TextField(help_text='The teaching content shown to the learner.')

    class Meta:
        ordering = ['language', 'lesson_order']
        unique_together = ('language', 'lesson_order')

    def __str__(self):
        return f'{self.language.name} #{self.lesson_order}: {self.title}'


class VocabularyItem(models.Model):
    """
    A single word/phrase pair shown to the learner during a lesson.
    Displayed as the term ABOVE its translation (not side-by-side columns).
    """
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='vocabulary_items')
    order = models.PositiveIntegerField(default=1)
    term = models.CharField(max_length=100, help_text='The word/phrase in the language being learned.')
    translation = models.CharField(max_length=150, help_text='The English meaning.')

    class Meta:
        ordering = ['lesson', 'order']

    def __str__(self):
        return f'{self.term} = {self.translation}'


class QuizQuestion(models.Model):
    """
    A short end-of-lesson quiz question. Displayed as the question ABOVE
    its answer (the answer is revealed below, not shown side-by-side).
    """
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='quiz_questions')
    order = models.PositiveIntegerField(default=1)
    question = models.CharField(max_length=255)
    answer = models.CharField(max_length=255)

    class Meta:
        ordering = ['lesson', 'order']

    def __str__(self):
        return f'Q{self.order}: {self.question}'


class LearningProfile(models.Model):
    """
    LearningProfile: ProfileID (PK), UserID (FK), LanguageID (FK),
    CurrentLesson, Proficiency. One profile per user (the "has" 1:1
    relationship in the ER diagram).
    """
    BEGINNER = 'beginner'
    INTERMEDIATE = 'intermediate'
    ADVANCED = 'advanced'
    PROFICIENCY_CHOICES = [
        (BEGINNER, 'Beginner'),
        (INTERMEDIATE, 'Intermediate'),
        (ADVANCED, 'Advanced'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='learning_profile')
    language = models.ForeignKey(Language, on_delete=models.CASCADE, related_name='profiles')
    proficiency = models.CharField(max_length=20, choices=PROFICIENCY_CHOICES, default=BEGINNER)
    current_lesson = models.ForeignKey(
        Lesson, on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )

    def __str__(self):
        return f'{self.user.username} learning {self.language.name} ({self.proficiency})'


class LearningProgress(models.Model):
    """
    LearningProgress: ProgressID (PK), UserID (FK), LessonID (FK),
    Status, Completed.
    """
    NOT_STARTED = 'not_started'
    IN_PROGRESS = 'in_progress'
    COMPLETED = 'completed'
    STATUS_CHOICES = [
        (NOT_STARTED, 'Not started'),
        (IN_PROGRESS, 'In progress'),
        (COMPLETED, 'Completed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='progress_records')
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='progress_records')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=IN_PROGRESS)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('user', 'lesson')

    def __str__(self):
        return f'{self.user.username} / {self.lesson} / {self.status}'
