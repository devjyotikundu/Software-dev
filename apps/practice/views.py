from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import TemplateView

from apps.languages.models import Language

from .forms import AnswerForm, StartForm
from .models import PracticeAnswer, PracticeSession, UserProgress
from .services import sessions as svc
from .services import proficiency
from .services.answers import InvalidAnswer, public_question
from .services.config import proficiency_setting


def _mix_labels(plan):
    """[("Level 3", 2), ("Level 4", 6), ...] for the "Why this level?" panel."""
    if not plan:
        return []
    return [(f"Level {rank}", count) for rank, count in plan.distribution.items()]


class OwnSessionMixin(LoginRequiredMixin):
    """Load a session that belongs to the signed-in user; anything else is a 404."""

    def get_session(self):
        return get_object_or_404(
            PracticeSession.objects.select_related("language"),
            pk=self.kwargs["pk"], user=self.request.user,
        )


class PracticeHomeView(LoginRequiredMixin, TemplateView):
    template_name = "practice/home.html"

    def get_context_data(self, **kwargs):
        user = self.request.user
        progress = {p.language_id: p for p in UserProgress.objects.filter(user=user)}
        active = {s.language_id: s for s in PracticeSession.objects.filter(
            user=user, status=PracticeSession.Status.IN_PROGRESS)}
        languages = []
        for lang in svc.learning_languages(user):
            plan = svc.plan_session(user, lang)
            languages.append({
                "language": lang, "progress": progress.get(lang.pk), "active": active.get(lang.pk),
                "plan": plan, "plan_level": svc.level_for_rank(plan.center) if plan else None,
                "plan_mix": _mix_labels(plan),
            })
        history = (
            PracticeSession.objects.filter(user=user, status=PracticeSession.Status.COMPLETED)
            .select_related("language").order_by("-completed_at")[:8]
        )
        return super().get_context_data(**kwargs, languages=languages, history=history)


class StartSessionView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request):
        form = StartForm(request.POST)
        language = None
        if form.is_valid():
            language = Language.objects.filter(code=form.cleaned_data["language"], is_active=True).first()
        if language is None:
            messages.error(request, "Choose a language to practise.")
            return redirect("practice:home")
        try:
            session = svc.start_session(request.user, language)
        except svc.PracticeError as error:
            messages.error(request, str(error))
            return redirect("practice:home")
        return redirect("practice:session", pk=session.pk)


class SessionView(OwnSessionMixin, TemplateView):
    """Shows the next unanswered question."""

    template_name = "practice/question.html"

    def get(self, request, *args, **kwargs):
        self.session = self.get_session()
        if self.session.status == PracticeSession.Status.COMPLETED:
            return redirect("practice:results", pk=self.session.pk)
        if self.session.status == PracticeSession.Status.ABANDONED:
            messages.info(request, "That session was ended. Start a new one when you're ready.")
            return redirect("practice:home")
        self.answer = svc.next_answer(self.session)
        if self.answer is None:  # defensive: all answered but not marked complete
            return redirect("practice:results", pk=self.session.pk)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, form=None, **kwargs):
        position = self.answer.position
        total = self.session.question_count
        return super().get_context_data(
            **kwargs,
            session=self.session,
            answer=self.answer,
            question=public_question(self.answer.question),
            form=form or AnswerForm(initial={"answer_id": self.answer.pk}),
            position=position, total=total,
            progress_percent=round((position - 1) / total * 100),
        )


class AnswerView(OwnSessionMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        session = self.get_session()
        form = AnswerForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Choose an answer first.")
            return redirect("practice:session", pk=session.pk)
        try:
            result = svc.submit_answer(session, form.cleaned_data["answer_id"], form.cleaned_data["option"])
        except InvalidAnswer as error:
            messages.error(request, str(error))
            return redirect("practice:session", pk=session.pk)
        except svc.PracticeError:
            # Usually a refreshed or duplicate submission: carry on where they are.
            return redirect("practice:session", pk=session.pk)
        if result.level_change:
            old, new = result.level_change
            if old:
                messages.success(request, f"Your estimated proficiency moved from {old} to {new}.")
            else:
                messages.success(request, f"You now have an estimated proficiency from practice: {new}.")
        return redirect("practice:feedback", pk=session.pk, position=result.answer.position)


class FeedbackView(OwnSessionMixin, TemplateView):
    template_name = "practice/feedback.html"

    def get(self, request, *args, **kwargs):
        self.session = self.get_session()
        self.answer = get_object_or_404(
            PracticeAnswer.objects.select_related("question__language", "question__category", "difficulty"),
            session=self.session, position=kwargs["position"],
        )
        if self.answer.answered_at is None:  # no peeking at feedback before answering
            return redirect("practice:session", pk=self.session.pk)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        question = self.answer.question
        is_last = self.answer.position >= self.session.question_count
        return super().get_context_data(
            **kwargs, session=self.session, answer=self.answer, question=question,
            options=question.options, total=self.session.question_count,
            is_last=is_last, progress_percent=round(self.answer.position / self.session.question_count * 100),
            streak_bonus=max(0, self.answer.xp_awarded - (self.answer.difficulty.xp_reward if self.answer.is_correct else 0)),
        )


class ResultsView(OwnSessionMixin, TemplateView):
    template_name = "practice/results.html"

    def get(self, request, *args, **kwargs):
        self.session = self.get_session()
        if self.session.status != PracticeSession.Status.COMPLETED:
            raise Http404("Results appear once a session is finished.")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        answers = self.session.answers.select_related("question", "difficulty").order_by("position")
        plan = svc.plan_session(self.session.user, self.session.language)
        row, estimate = proficiency.estimate_for(self.session.user, self.session.language)
        return super().get_context_data(
            estimate=estimate, learning_row=row,
            min_answers=proficiency_setting("MIN_ANSWERS"),
            **kwargs, session=self.session, answers=answers,
            summary=svc.performance_summary(self.session),
            recommended=svc.level_for_rank(plan.center) if plan else None,
            plan=plan, plan_mix=_mix_labels(plan),
        )


class QuitView(OwnSessionMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        if svc.abandon_session(self.get_session()):
            messages.info(request, "Session ended. XP you earned so far has been kept.")
        return redirect("practice:home")
