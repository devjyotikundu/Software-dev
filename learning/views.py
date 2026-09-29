import json
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .forms import ProfileSetupForm
from .models import Lesson, LearningProfile, LearningProgress


def _wants_json(request):
    return request.content_type == 'application/json'


def _next_incomplete_lesson(profile):
    """First lesson in the profile's language that the user hasn't completed."""
    done_lesson_ids = LearningProgress.objects.filter(
        user=profile.user, lesson__language=profile.language, completed=True
    ).values_list('lesson_id', flat=True)
    return (
        Lesson.objects.filter(language=profile.language)
        .exclude(id__in=done_lesson_ids)
        .order_by('lesson_order')
        .first()
    )


@login_required
@csrf_exempt
@require_http_methods(['GET', 'POST'])
def profile_setup(request):
    """
    GET  -> render the "Start Learning" page (select language + proficiency)
    POST -> POST /learning/profile/
            Given: authenticated user + valid language
            Then: 200/201, LanguageID and Level saved
    """
    profile = LearningProfile.objects.filter(user=request.user).first()

    if request.method == 'GET':
        form = ProfileSetupForm(instance=profile)
        return render(request, 'learning/profile_setup.html', {'form': form})

    if _wants_json(request):
        data = json.loads(request.body or '{}')
    else:
        data = request.POST

    form = ProfileSetupForm(data, instance=profile)
    if form.is_valid():
        was_new = profile is None
        profile = form.save(commit=False)
        profile.user = request.user
        profile.current_lesson = _next_incomplete_lesson(profile) if profile.language_id else None
        profile.save()

        payload = {
            'language_id': profile.language_id,
            'proficiency': profile.proficiency,
        }
        status_code = 201 if was_new else 200
        if _wants_json(request):
            return JsonResponse(payload, status=status_code)
        return redirect('learning:next_lesson')

    if _wants_json(request):
        return JsonResponse({'errors': form.errors}, status=400)
    return render(request, 'learning/profile_setup.html', {'form': form})


@login_required
def next_lesson(request):
    """
    GET /learning/next-lesson/
    Given: authenticated user with incomplete lessons
    Then: 200 with LessonID, Title, LessonOrder, Content
    """
    profile = LearningProfile.objects.filter(user=request.user).first()
    if profile is None:
        if _wants_json(request):
            return JsonResponse({'error': 'No learning profile yet'}, status=404)
        return redirect('learning:profile_setup')

    lesson = _next_incomplete_lesson(profile)

    if lesson is None:
        if _wants_json(request):
            return JsonResponse({'message': 'Course complete'}, status=200)
        return render(request, 'learning/course_complete.html', {'language': profile.language})

    vocabulary_items = lesson.vocabulary_items.all()
    quiz_questions = lesson.quiz_questions.all()

    if _wants_json(request):
        return JsonResponse({
            'lesson_id': lesson.id,
            'title': lesson.title,
            'lesson_order': lesson.lesson_order,
            'contents': lesson.contents,
            'vocabulary': [
                {'term': v.term, 'translation': v.translation} for v in vocabulary_items
            ],
            'quiz': [
                {'question': q.question, 'answer': q.answer} for q in quiz_questions
            ],
        }, status=200)
    return render(request, 'learning/lesson.html', {
        'lesson': lesson,
        'language': profile.language,
        'vocabulary_items': vocabulary_items,
        'quiz_questions': quiz_questions,
    })


@login_required
@csrf_exempt
@require_http_methods(['POST'])
def mark_progress(request):
    """
    POST /learning/progress/
    Given: authenticated user + valid lesson
    Then: progress and completion time saved
    """
    if _wants_json(request):
        data = json.loads(request.body or '{}')
    else:
        data = request.POST

    lesson_id = data.get('lesson_id')
    lesson = get_object_or_404(Lesson, id=lesson_id)

    progress, _ = LearningProgress.objects.get_or_create(user=request.user, lesson=lesson)
    progress.status = LearningProgress.COMPLETED
    progress.completed = True
    progress.completed_at = timezone.now()
    progress.save()

    # Advance the profile's pointer to whatever the new next lesson is.
    profile = LearningProfile.objects.filter(user=request.user).first()
    if profile:
        profile.current_lesson = _next_incomplete_lesson(profile)
        profile.save()

    payload = {
        'lesson_id': lesson.id,
        'completed': True,
        'completed_at': progress.completed_at.isoformat(),
    }
    if _wants_json(request):
        return JsonResponse(payload, status=200)
    return redirect('learning:next_lesson')
