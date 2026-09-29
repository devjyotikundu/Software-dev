from django.contrib import admin

from .models import (
    DifficultyLevel, PracticeAnswer, PracticeQuestion, PracticeSession,
    QuestionCategory, UserCategoryStat, UserProgress,
)


@admin.register(DifficultyLevel)
class DifficultyLevelAdmin(admin.ModelAdmin):
    list_display = ("label", "code", "rank", "xp_reward", "is_active")
    list_editable = ("xp_reward", "is_active")
    ordering = ("rank",)


@admin.register(QuestionCategory)
class QuestionCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "sort_order")
    list_editable = ("is_active", "sort_order")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(PracticeQuestion)
class PracticeQuestionAdmin(admin.ModelAdmin):
    list_display = (
        "short_text", "language", "difficulty", "category",
        "source", "is_verified", "is_active",
    )
    list_filter = ("language", "difficulty", "category", "source", "is_verified", "is_active")
    ordering = ("language", "difficulty__rank", "pk")
    list_editable = ("is_active",)
    search_fields = ("question_text", "english_meaning")
    list_select_related = ("language", "difficulty", "category")
    readonly_fields = ("content_hash", "created_at", "updated_at")
    actions = ("enable_questions", "disable_questions", "mark_reviewed", "mark_needs_review")

    @admin.display(description="Question")
    def short_text(self, obj):
        return obj.question_text[:70]

    @admin.action(description="Enable selected questions")
    def enable_questions(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_active=True)} questions enabled.")

    @admin.action(description="Disable selected questions")
    def disable_questions(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_active=False)} questions disabled.")

    @admin.action(description="Mark as reviewed by a fluent speaker")
    def mark_reviewed(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_verified=True)} questions marked reviewed.")

    @admin.action(description="Mark as needing review")
    def mark_needs_review(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_verified=False)} questions marked for review.")


class PracticeAnswerInline(admin.TabularInline):
    model = PracticeAnswer
    extra = 0
    can_delete = False
    readonly_fields = (
        "position", "question", "difficulty", "selected_option",
        "is_correct", "xp_awarded", "answered_at",
    )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(PracticeSession)
class PracticeSessionAdmin(admin.ModelAdmin):
    list_display = ("user", "language", "status", "correct_count", "xp_earned", "created_at")
    list_filter = ("status", "language")
    search_fields = ("user__username",)
    list_select_related = ("user", "language")
    inlines = [PracticeAnswerInline]


@admin.register(UserProgress)
class UserProgressAdmin(admin.ModelAdmin):
    list_display = ("user", "language", "total_xp", "questions_answered",
                    "correct_answers", "sessions_completed")
    list_filter = ("language",)
    search_fields = ("user__username",)
    list_select_related = ("user", "language")


@admin.register(UserCategoryStat)
class UserCategoryStatAdmin(admin.ModelAdmin):
    list_display = ("user", "language", "category", "questions_answered", "correct_answers")
    list_filter = ("language", "category")
    list_select_related = ("user", "language", "category")
