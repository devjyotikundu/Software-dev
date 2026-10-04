"""Load users as MatchProfile snapshots in a fixed number of queries."""
from django.contrib.auth import get_user_model
from django.db.models import Prefetch

from apps.profiles.models import UserLanguage

from .scoring import MatchProfile


def load_profiles(user_ids):
    users = (
        get_user_model().objects.filter(pk__in=user_ids)
        .select_related("profile")
        .prefetch_related(
            Prefetch("languages", queryset=UserLanguage.objects.select_related(
                "language", "self_declared_level", "assessed_level")),
            "profile__goals", "profile__interests", "profile__communication_modes",
            "profile__availability_slots",
        )
    )
    return {user.pk: snapshot(user) for user in users}


def snapshot(user):
    profile = user.profile
    native, learning = {}, {}
    for row in user.languages.all():
        if row.role == UserLanguage.Role.NATIVE:
            native[row.language_id] = row.language.name
        else:
            rank = row.current_rank
            code = next((lvl.code for lvl in (row.self_declared_level, row.assessed_level)
                         if lvl is not None and lvl.rank == rank), None)
            learning[row.language_id] = (row.language.name, rank, code or _code_for_rank(rank))
    return MatchProfile(
        user_id=user.pk, display_name=profile.display_name, native=native, learning=learning,
        goals={g.pk: g.name for g in profile.goals.all()},
        interests={i.pk: i.name for i in profile.interests.all()},
        modes={m.pk: m.name for m in profile.communication_modes.all()},
        timezone=profile.timezone,
        slots=[(s.weekday, s.start_time, s.end_time) for s in profile.availability_slots.all()],
    )


def _code_for_rank(rank):
    return {1: "A1", 2: "A2", 3: "B1", 4: "B2", 5: "C1", 6: "C2"}.get(rank)
