from django.contrib import admin
from .models import (
    Language,
    Lesson,
    VocabularyItem,
    QuizQuestion,
    LearningProfile,
    LearningProgress,
)

admin.site.register(Language)
admin.site.register(Lesson)
admin.site.register(VocabularyItem)
admin.site.register(QuizQuestion)
admin.site.register(LearningProfile)
admin.site.register(LearningProgress)
