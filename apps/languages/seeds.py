from apps.core.seeding import seed_reference

from .models import Language, ProficiencyLevel

LANGUAGES = [
    {"code": "en", "name": "English", "native_name": "English", "sort_order": 1},
    {"code": "bn", "name": "Bengali", "native_name": "বাংলা", "sort_order": 2},
    {"code": "hi", "name": "Hindi", "native_name": "हिन्दी", "sort_order": 3},
]

PROFICIENCY_LEVELS = [
    {"code": "A1", "rank": 1, "name": "Beginner",
     "description": "Understands and uses familiar everyday expressions."},
    {"code": "A2", "rank": 2, "name": "Elementary",
     "description": "Handles simple, routine exchanges on familiar topics."},
    {"code": "B1", "rank": 3, "name": "Intermediate",
     "description": "Deals with most everyday situations and describes experiences."},
    {"code": "B2", "rank": 4, "name": "Upper-intermediate",
     "description": "Talks with fluency and spontaneity with native speakers."},
    {"code": "C1", "rank": 5, "name": "Advanced",
     "description": "Expresses ideas fluently for social, academic and work purposes."},
    {"code": "C2", "rank": 6, "name": "Mastery",
     "description": "Understands virtually everything; near-native precision."},
]


def seed(*, update, **_options):
    return {
        "Languages": seed_reference(Language, LANGUAGES, key="code", update=update),
        "Proficiency levels": seed_reference(
            ProficiencyLevel, PROFICIENCY_LEVELS, key="code", update=update
        ),
    }
