from django.contrib import admin
from .models import Language, Lesson, LearningProfile, LearningProgress

admin.site.register(Language)
admin.site.register(Lesson)
admin.site.register(LearningProfile)
admin.site.register(LearningProgress)
