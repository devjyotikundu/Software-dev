"""Turn stored profile data into short, human-readable summaries for templates."""
from collections import defaultdict


def summarize_availability(slots):
    """Group days that share the same time ranges.

    [Mon 17–21, Wed 17–21, Sat 06–12] ->
    [("Mon, Wed", "17:00–21:00"), ("Sat", "06:00–12:00")]
    """
    ranges_by_day = defaultdict(list)
    for slot in slots:
        ranges_by_day[slot.weekday].append(f"{slot.start_time:%H:%M}–{slot.end_time:%H:%M}")

    days_by_ranges = defaultdict(list)
    labels = {}
    for slot in slots:
        labels[slot.weekday] = slot.get_weekday_display()[:3]
    for day in sorted(ranges_by_day):
        days_by_ranges[", ".join(ranges_by_day[day])].append(labels[day])

    return [(", ".join(days), ranges) for ranges, days in days_by_ranges.items()]


def profile_summary(profile):
    """Everything the profile summary partial needs, in as few queries as practical."""
    return {
        "profile": profile,
        "user_languages": profile.user.languages.select_related(
            "language", "self_declared_level", "assessed_level"
        ).order_by("-role", "language__sort_order"),  # native first
        "goals": profile.goals.all(),
        "interests": profile.interests.all(),
        "communication_modes": profile.communication_modes.all(),
        "availability": summarize_availability(profile.availability_slots.all()),
        "learning_progress": learning_progress(profile.user),
    }


def learning_progress(user):
    """Practice totals for each language the user is learning (zeros if none yet)."""
    from apps.practice.models import UserProgress  # practice depends on profiles, not the reverse

    totals = {p.language_id: p for p in UserProgress.objects.filter(user=user)}
    rows = []
    for row in user.languages.filter(role="learning").select_related("language").order_by("language__sort_order"):
        progress = totals.get(row.language_id)
        answered = progress.questions_answered if progress else 0
        rows.append({
            "language": row.language,
            "xp": progress.total_xp if progress else 0,
            "answered": answered,
            "accuracy": round(progress.correct_answers / answered * 100) if answered else None,
            "sessions": progress.sessions_completed if progress else 0,
        })
    return rows
