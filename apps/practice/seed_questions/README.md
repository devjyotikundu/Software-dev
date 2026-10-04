# Seed questions

`en.json`, `bn.json` and `hi.json` hold the curated question bank:
10 difficulty levels × 10 questions × 3 languages = 300 questions, loaded by
`python manage.py seed_data`. The format is documented in
`apps/practice/question_loader.py`.

Each level covers all six categories (vocabulary, grammar, sentence
completion, context, reading comprehension, everyday expressions), and the
correct answers are spread evenly across A–D.

The Bengali and Hindi questions were written for each language, not
translated from English: they test registers (আপনি/তুমি/তুই, आप/तुम/तू),
classifiers, gender and ergative agreement, সন্ধি/संधि, সমাস/समास and native
idioms. They are loaded with `verified: false`, meaning "not yet reviewed by a
fluent speaker". They are still served. Review them in the admin and use the
"Mark as reviewed" action. Fix wording in the admin. (Editing a question in
these files and re-seeding adds it as a new question, because questions are
matched by content; disable the old one in the admin if you do that.)

Check coverage at any time with `python manage.py question_bank_report`.
