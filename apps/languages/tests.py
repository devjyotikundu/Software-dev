from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.core.testing import seed_reference_data

from .models import Language, ProficiencyLevel


class LanguageModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_reference_data()

    def test_codes_are_unique(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Language.objects.create(code="en", name="Duplicate", native_name="Duplicate")

    def test_active_filter(self):
        Language.objects.filter(code="hi").update(is_active=False)
        self.assertEqual(
            set(Language.objects.active().values_list("code", flat=True)), {"en", "bn"}
        )

    def test_adding_a_language_is_data_only(self):
        Language.objects.create(code="ta", name="Tamil", native_name="தமிழ்")
        self.assertEqual(Language.objects.count(), 4)

    def test_proficiency_levels_are_ranked(self):
        ranks = list(ProficiencyLevel.objects.values_list("rank", flat=True))
        self.assertEqual(ranks, [1, 2, 3, 4, 5, 6])
