from apps.core.seeding import seed_reference

from .models import CommunicationMode, Interest, LearningGoal

GOALS = [
    ("speaking", "Speaking practice"), ("vocabulary", "Vocabulary"),
    ("grammar", "Grammar"), ("travel", "Travel"), ("academic", "Academic"),
    ("interview", "Interview preparation"),
    ("casual-conversation", "Casual conversation"), ("pronunciation", "Pronunciation"),
]

INTERESTS = [
    ("technology", "Technology"), ("music", "Music"), ("movies", "Movies"),
    ("sports", "Sports"), ("travel", "Travel"), ("books", "Books"),
    ("food", "Food"), ("art", "Art"), ("science", "Science"),
    ("gaming", "Gaming"), ("photography", "Photography"), ("history", "History"),
    ("nature", "Nature"), ("fitness", "Fitness"),
]

COMMUNICATION_MODES = [("text", "Text"), ("voice", "Voice"), ("video", "Video")]


def _rows(pairs):
    return [{"slug": s, "name": n, "sort_order": i} for i, (s, n) in enumerate(pairs, 1)]


def seed(*, update, **_options):
    return {
        "Learning goals": seed_reference(LearningGoal, _rows(GOALS), key="slug", update=update),
        "Interests": seed_reference(Interest, _rows(INTERESTS), key="slug", update=update),
        "Communication modes": seed_reference(
            CommunicationMode, _rows(COMMUNICATION_MODES), key="slug", update=update
        ),
    }
