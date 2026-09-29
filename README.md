# Language Exchange Matcher

A web application that connects people who want to learn each other's languages.

**Assess → Understand → Match → Exchange → Feedback → Improve**

A Bengali speaker learning English is matched with an English speaker learning
Bengali. Each helps the other. Practice quizzes estimate each user's level,
the matching engine finds reciprocal partners and explains why they match, and
feedback from real exchanges improves future recommendations.

> Status: **Phase 14 (AI services) complete.** Features are added phase by
> phase; see [Development phases](#development-phases).

## Technology stack

| Area | Choice | Why |
|---|---|---|
| Backend | Python, Django 5.2 LTS, Django REST Framework | One framework for pages, API, admin and auth |
| Database | PostgreSQL | Relational data with constraints and indexes |
| Frontend | HTML, CSS, JavaScript, Bootstrap 5 | Server-rendered pages; no separate frontend build |
| Real-time | Django Channels, WebSockets, Redis | Private exchange rooms |
| Background jobs | Celery, Redis | Added in Phase 15 |
| AI | External LLM API, called only from the backend | Optional helper and question drafts |
| Hosting | Render (portable to AWS/Azure/GCP) | Configured in Phases 19–20 |

## Project structure

```
language-exchange-matcher/
├── manage.py
├── requirements.txt
├── .env.example            # copy to .env; never commit .env
├── config/
│   ├── settings/
│   │   ├── base.py         # shared settings
│   │   ├── development.py  # local (default for manage.py)
│   │   ├── test.py         # automated tests
│   │   └── production.py   # deployed (default for wsgi/asgi)
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── apps/
│   ├── core/               # home page, health check, error pages
│   ├── accounts/           # custom User model
│   ├── languages/          # languages, proficiency reference data
│   ├── profiles/           # profile, goals, interests, availability
│   ├── practice/           # questions, sessions, XP, adaptive difficulty
│   ├── matching/           # filtering, scoring, explanations, requests
│   ├── exchange/           # rooms, messages, sessions
│   ├── feedback/           # post-session feedback
│   ├── notifications/      # notifications
│   └── ai_services/        # optional AI assistance with fallbacks
├── templates/              # base layout, partials, error pages
└── static/                 # CSS, images
```

Each app owns one area of the product. Business logic will live in a
`services` module inside the relevant app (for example
`apps/matching/services/`), not in views or templates.

## Local setup

Requirements: Python 3.12+, PostgreSQL 14+.

```bash
# 1. Virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Database (psql or pgAdmin)
createdb language_exchange

# 3. Configuration
cp .env.example .env               # then edit SECRET_KEY and DATABASE_URL

# 4. Database tables and reference data
python manage.py migrate
python manage.py seed_data
python manage.py createsuperuser

# 5. Run
python manage.py runserver
```

Open http://127.0.0.1:8000. The admin is at `/admin/` (or your `ADMIN_URL`).
The health check is at `/health/`.

Generate a secret key with:

```bash
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

## Database design

All tables live in PostgreSQL. Lookup values (languages, levels, goals,
interests, categories) are rows, not code, so adding Tamil or a new interest
is a data change only.

| App | Models | Purpose |
|---|---|---|
| languages | `Language`, `ProficiencyLevel` | Supported languages; estimated levels A1–C2 with a numeric rank |
| profiles | `Profile`, `UserLanguage`, `LearningGoal`, `Interest`, `CommunicationMode`, `AvailabilitySlot` | Who the user is, which languages they speak or learn, and their preferences |
| practice | `DifficultyLevel`, `QuestionCategory`, `PracticeQuestion`, `PracticeSession`, `PracticeAnswer`, `UserProgress`, `UserCategoryStat` | Question bank, practice history, XP and per-category strengths |
| matching | `MatchSuggestion`, `MatchRequest`, `Match` | Precomputed scores, requests, confirmed partnerships |
| exchange | `ExchangeRoom`, `Message`, `ExchangeSession` | Private rooms, chat, timed sessions |
| feedback | `SessionFeedback` | Post-session ratings |
| notifications | `Notification` | In-app notifications |
| accounts | `User`, `BlockedUser`, `Report` | Accounts and safety |

Rules the database itself enforces, so no bug in a view can break them:

- A user's language is either native or learning, never both; native languages carry no level.
- One unfinished practice session per user and language; each answer is either fully recorded or not at all.
- Duplicate questions (same normalised text and options) are rejected per language.
- One pending request per sender and receiver; nobody can request, block, report or review themselves.
- A match stores its pair in a fixed order (lower user id first), so two people can never have two active matches.
- One active session per exchange room, 1–60 minutes per language, ending after it starts.
- Feedback ratings are 1–5, once per person per session.

Questions that have been answered cannot be deleted (admins disable them
instead), and reports and feedback survive account deletion.

Name mapping from the project brief: `PracticeAttempt` → `PracticeSession`;
`UserInterest` and `UserGoal` are the many-to-many tables on `Profile`;
`Availability` → `AvailabilitySlot`; `Feedback` → `SessionFeedback`.

**Difficulty is not proficiency.** `DifficultyLevel` (codes A1–A10, shown as
"Level 1"–"Level 10") rates questions for the game and holds the XP reward.
`ProficiencyLevel` (A1–C2) is the user's estimated ability. They are separate
tables and never share a field.

## Accounts and onboarding

People sign up with their name, email and password, then complete five
short onboarding steps: languages (native, learning, self-declared level),
goals, interests, availability (time zone, days, times of day) and how they'd
like to practise.

- **Email sign-in.** Emails are unique regardless of capitalisation, enforced
  by the database. A hidden username is generated for each account; the
  admin can still sign in by username.
- **Registration is atomic.** The account and its profile are created in one
  transaction (`apps/accounts/services.py`), so there is never an account
  without a profile, or the reverse.
- **Onboarding progress lives in the data.** A step is complete when its
  data exists, so progress survives logging out, later steps can't be reached
  early, and nobody finishes by skipping. Until onboarding is finished, a
  middleware sends signed-in users back to it (account pages, logout and the
  admin stay reachable).
- **Passwords.** At least 10 characters and checked against common
  passwords; change and reset flows included. Reset links expire after two
  hours, and the reset page never reveals whether an email is registered.
  Logout only works by POST, so a link on another site can't sign people out.
- In local development, reset emails are printed to the console.

## Profile

`/profile/` shows everything used for matching, with an edit page per section:
about (name, bio, photo), languages, goals, interests, availability, practice
style and privacy. Business rules live in `apps/profiles/services.py`.

- **Languages.** Up to three native and three learning languages. A profile
  always keeps at least one of each, so it stays matchable. Learners set a
  self-declared level; the assessed level is written only by the proficiency
  engine (Phase 8).
- **Availability.** Exact weekly time ranges in the user's time zone,
  validated so ranges on the same day can't overlap and at least one remains.
- **Photos** are checked to be real JPEG, PNG or WebP images under 2 MB, then
  re-encoded as a 400×400 JPEG with a random file name. Re-encoding removes
  EXIF data such as GPS location. Replaced photos are deleted from storage.
- **Privacy.** Users can hide themselves from partner suggestions. Emails are
  never shown to other users.
- **Account deletion** requires the password. It removes the profile,
  languages, practice history, matches, rooms and messages; feedback and
  safety reports the user wrote are kept without their name.

Every profile URL acts only on the signed-in user's own data; other users'
records return 404.

## Practice questions

The curated bank holds 300 multiple-choice questions: 10 difficulty levels ×
10 questions × English, Bengali and Hindi. Every level covers all six
categories, and correct answers are spread evenly across A–D. Bengali and
Hindi questions are written for each language (registers, classifiers,
gender and ergative agreement, সন্ধি/संधि, সমাস/समास, native idioms), not
translated from English. See `apps/practice/seed_questions/README.md`.

- **What learners can see** is defined once, in
  `PracticeQuestion.objects.servable()`: active questions at an active level;
  bank questions always, AI-generated ones only after review.
- **Choosing questions** (`apps/practice/services/questions.py`) picks random
  questions at the requested level, avoiding the learner's last 30 answers,
  and widens to the nearest levels if the bank is short. It uses two queries
  however large the bank grows.
- **Checking answers** (`apps/practice/services/answers.py`) happens only on
  the server. The data sent to the browser before answering contains no
  correct option, meaning or explanation.
- `python manage.py question_bank_report` shows coverage per language and level.

## Practice game and XP

`/practice/` lists the languages a user is learning with their XP and
accuracy. A session is 10 questions: one question per screen, then instant
feedback (correct or not, the right answer, the English meaning, a short
explanation and the XP earned), then a results page with score, accuracy,
XP, a plain-language verdict and the suggested level for next time.

- **XP is decided only on the server** (`apps/practice/services/xp.py`).
  The browser sends just the question id and the letter chosen; any other
  field is ignored. Base XP comes from the question's level (editable in the
  admin); wrong answers earn 0; every third correct answer in a row adds a
  5 XP streak bonus. Both bonus values are in `settings.PRACTICE`.
- **No double counting.** Each answer is recorded in a transaction with the
  row locked, answers must be given in order, and every submit redirects to
  a separate feedback page, so refreshing or double-clicking never awards
  XP twice.
- **Progress** (`UserProgress`, `UserCategoryStat`) is updated in the same
  transaction as the answer, so totals are always consistent. Profiles show
  a Learning progress section per language.
- A session can be resumed after leaving the page, or ended early (XP earned
  so far is kept). Other users' sessions return 404.

## Adaptive difficulty

Each session's level mix is chosen by `apps/practice/services/adaptive.py`,
in two separate steps: `gather_evidence` reads the learner's history and
`decide` applies the rules to it without touching the database, which keeps
the rules easy to test and to replace later.

1. **Start** from the average level of the last finished session, or, the
   first time, from the learner's CEFR estimate mapped to a game level
   (A1 → Level 1, B1 → Level 4, C2 → Level 9).
2. **Step** by accuracy over the last 10 answers: 85%+ up one level, 70%+
   up half a level, 55% or less down half, 40% or less down one. A clear
   trend over the last 20 answers adds a quarter level either way. The move
   is capped at one level per session, so there are no sudden jumps.
3. **XP unlocks the top levels** (up to Level 6 from the start, 7 at 300 XP,
   8 at 800, 9 at 1,500, 10 at 2,500), matching the brief: low XP means
   mostly easier levels, very high XP the hardest.
4. **Mix** the session around the target: normally 60% at the target and
   20% a level either side; leaning easier when struggling and harder when
   doing well. Fractional targets blend two levels, so half steps really
   add up at half speed. Questions run from easier to harder.
5. **Weak areas**: up to 30% of questions come from categories with under
   60% accuracy (after at least 5 answers).

All numbers are in `settings.PRACTICE["ADAPTIVE"]`. The practice page shows
"Why this level?" with the actual reasons ("Your last 10 answers: 90%
correct, so we're stepping up") and the question mix.

**Viva summary:** the level moves like a thermostat. Recent accuracy
decides the direction, a cap keeps each change small, XP limits how high a
new account can go, and weak topics get extra attention.

## Proficiency estimation

`apps/practice/services/proficiency.py` estimates each learner's A1–C2
level from their practice answers. **In one sentence: we find the level that
best explains your right and wrong answers.**

- **Model.** A one-parameter item-response ("Rasch") model, the family used
  by adaptive standardised tests: the chance of answering a Level d question
  correctly rises smoothly as the learner's ability θ rises. θ is defined
  as the "comfortable level" where the learner gets about 70% right.
- **Fit.** θ is the value on a 0.5–10.5 grid that makes the learner's actual
  answers most likely. Newer answers count more (weights halve every 50
  answers), and the self-declared level acts as a gentle starting belief
  that fades as data grows. Pure Python, about 50 ms for 300 answers.
- **Level.** θ maps to A1–C2 with thresholds consistent with the practice
  starting levels (B1 ≈ Level 4, B2 ≈ Level 6, C2 ≈ Level 9).
- **Confidence (0–1)** grows with the amount of evidence and drops when the
  latest 20 answers point to a different level than the full record (the
  consistency check).
- **Which level is shown.** `UserLanguage.current_level` blends the
  self-declared and assessed levels by confidence, so the assessed level
  gains weight as evidence grows and takes over at full confidence. No
  assessment exists before 20 answers.
- It is recalculated after every finished session; learners see a message
  when it changes, the results page explains it with the real numbers, and
  `python manage.py recalculate_proficiency` recomputes everyone after a
  settings change. All values are in `settings.PRACTICE["PROFICIENCY"]`.

These are application estimates for matching partners, not official CEFR
certification, and the UI says so.

## Matching engine

`apps/matching/services/` finds mutually useful partners. **Reciprocal**
means both directions must work: they can help with the language I'm
learning *and* I can help with the language they're learning. Someone who
only speaks my target language is not a match.

**1. Candidate filtering (SQL, `candidates.py`).** Nobody is compared with
everyone. Candidates must be active accounts with finished, discoverable
profiles, active in the last 90 days, and reciprocal ("can help" = native,
or learning it at C1 or above). Blocks in either direction, current
partners, pending requests and requests declined in the last 30 days are
excluded. Indexed columns make this one query; at most 500 of the most
recently active candidates are scored.

**2. Scoring (pure Python, `scoring.py`).** Six factors, each 0–100:

| Factor | Weight | How it's scored |
|---|---|---|
| Language | 40% | 100 if both speak the other's target natively; 80 per side for a C1+ learner |
| Proficiency | 20% | Difference between the two learners' levels: 0 → 100, 1 → 90, 2 → 70, 3 → 50, 4+ → 30 |
| Goals | 15% | Jaccard similarity: shared ÷ all distinct goals |
| Interests | 10% | Jaccard similarity of interests |
| Availability | 10% | Weekly overlap in minutes (both converted to UTC, time zones and daylight saving handled) ÷ the smaller schedule |
| Communication | 5% | Jaccard similarity of text/voice/video preferences |

`Match score = 0.40 × language + 0.20 × proficiency + 0.15 × goals +
0.10 × interests + 0.10 × availability + 0.05 × communication`. Weights, the
proficiency table and every threshold are in `settings.MATCHING`. The score
is symmetric: A→B equals B→A.

**3. Stored suggestions (`suggestions.py`).** Results go into
`MatchSuggestion` with a breakdown of every factor's score and the facts
behind it, so pages don't recalculate on each request. Suggestions refresh
when older than 30 minutes or when the user edits their profile, and
`python manage.py compute_matches` recomputes everyone. The query count for
a refresh stays the same however many candidates there are.

**4. Explanations.** "Why this match?" text is generated only from the
stored breakdown, e.g. "You're learning English, which they speak
natively; they're learning Bengali, which you speak natively" or "You're
both free for about 3.5 hours a week, for example Monday 17:00–20:30 your
time", so an explanation can never disagree with its score.

Activity is recorded by a small middleware that writes `last_active_at` at
most once every 15 minutes per user.

## Discovering partners

- **`/discover/`** lists suggested partners, best match first, 12 per page.
  Each card shows only photo, name, the languages they speak and learn,
  their estimated level, common interests, a goal and the match percentage,
  with one action: **View match**. Four optional filters (language, goal,
  practice style, "free when I am") combine and stay in the page URL.
- **`/discover/<id>/`** shows the percentage, then **Why this match?**: a bar
  and one plain sentence per factor, all generated from the stored
  breakdown, plus a "How the % is calculated" table whose points add up to
  the score. Only people currently suggested to you can be opened; anyone
  else (including people who blocked you) returns 404.
- **Privacy.** Cards and detail pages never show email, username or the
  full weekly schedule, only the overlapping times.
- **Dashboard.** The signed-in home page shows only what the brief lists:
  the languages you're learning with estimated level and XP, your last
  practice, your top two partner suggestions, and two actions (Practice and
  Discover partners). The full profile lives on `/profile/`.
- Pages use a constant number of database queries however many partners
  are suggested.

## Match requests, partners and safety

**Suggested → Request sent → Accepted → Match confirmed → Exchange room
created.** Nobody becomes a partner until both agree. Business rules live
in `apps/matching/services/requests.py` and `safety.py`; every change runs
in a transaction with the row locked.

- **Send** (from a match page, with an optional note): only to someone
  currently suggested to you, which guarantees the pair is reciprocal, not
  blocked and not already connected. The language pair and score are
  copied from the suggestion. If they already asked you, sending back is
  mutual acceptance. At most 20 open sent requests at once.
- **Accept** (receiver only) creates the `Match` and its private
  `ExchangeRoom` together. **Decline** (receiver only) starts a 30-day
  cooldown; **Withdraw** (sender only). Which action runs is fixed by the
  URL, never by form data, and all three are POST-only.
- **Partners** (`/partners/`) lists confirmed partners; **Requests** shows
  received and sent requests, with a count badge in the header. Request
  and partner pages recompute "Why this match?" live, since pending and
  matched people leave the suggestion list.
- **Block** hides both people from each other everywhere, withdraws pending
  requests and ends a partnership (its room is closed). **Report** stores a
  confidential report for moderators, optionally blocking too. Both are
  only available for people you've actually come across, so user ids can't
  be probed. Blocked people can be managed and unblocked from the profile.

## Exchange rooms (real time)

Each confirmed partnership has a private room at `/rooms/<id>/`.

- **Live chat over WebSockets** (Django Channels). Messages are stored,
  then broadcast to both partners; a "typing…" hint goes to the other
  person only. Without JavaScript, or if the socket drops, the same form
  posts normally, and the page reconnects automatically with back-off.
- **Balanced sessions.** Either partner starts a session: choose which
  language goes first and 5–30 minutes per language. The timer (aligned
  to the server clock) switches from one language to the other halfway and
  shows the time left; each message is tagged with the language being
  practised. One session runs at a time; ending it records the duration.
- **Conversation ideas** come from the pair's shared interests, with
  general prompts as backup.
- **Security.** A socket must pass three checks: the page's origin must
  be one of our hosts (so other sites can't open sockets with a user's
  cookies), the Django session must identify the user, and the user must
  be one of the room's two partners in an active match (close codes 4401
  and 4403). The check is repeated on every message, so a block takes
  effect immediately even for an open room. Messages are limited to 2,000
  characters and 10 per 10 seconds per connection, and are rendered as
  text only (never as HTML) in both the page and the live updates.

**Redis.** `REDIS_URL` connects the channel layer to Redis so several
server processes share rooms; production refuses to start without it.
Locally it's optional: without it an in-memory layer is used, which works
with a single `runserver`. On Windows, Redis can run via Docker
(`docker run -p 6379:6379 redis:7`) or WSL, then set
`REDIS_URL=redis://localhost:6379/0`.

## Feedback

After a session ends, each partner answers four questions: how useful the
exchange was (1–5), whether they'd practise with that person again, whether
the difficulty was comfortable, and an optional comment. Ending a session
opens the form straight away; the other partner sees a "How did it go?"
prompt in the room until they answer. The form shows the session's length,
the languages practised and the messages sent in each. Each person can
answer once per session; answers are never shown to the partner.

**How feedback improves recommendations** (`apps/matching/services/feedback.py`,
separate from the unchanged six-factor formula):

- **"Wouldn't practise again"**, from either side, means the two are never
  suggested to each other again.
- **Reputation.** After at least 3 reviews, a person's average usefulness
  moves their match score by up to ±5 points (5/5 adds 5, 3/5 is neutral,
  1/5 takes 5 off), capped to 0–100. It appears as a "Partner feedback" line
  in "Why this match?", so the points still add up to the score.

Only anonymous averages are used; individual answers and comments are for
admins only. Both values are in `settings.MATCHING`.

## AI services (optional)

AI supports the human exchange; it never replaces it. With no provider
configured, AI features are switched off and hidden, and everything else
works as normal.

- **Configuration.** `AI_PROVIDER` is `anthropic` (Messages API) or
  `openai` (any OpenAI-compatible chat endpoint, with `AI_BASE_URL`), plus
  `AI_API_KEY` and `AI_MODEL`. The key is only used on the server; the
  client (`apps/ai_services/client.py`) uses Python's standard library, so
  there is no SDK dependency.
- **Room helper.** In a room, each partner can privately ask to explain a
  word, explain grammar, translate, say something more naturally, or get
  topic ideas; after a session they can get a private summary with useful
  vocabulary. Answers go only to the person who asked and are never posted
  into the chat. The prompt includes their languages and level; their text
  is wrapped in `<text>` tags and the model is told to treat it as material,
  never as instructions. Input is capped at 500 characters, use at 30
  requests per hour per person, and answers are shown as plain text.
- **Question generation** (`python manage.py generate_questions --language bn
  --level 5 --category grammar`, or `--for-user <id>` to target a learner's
  level and weakest category). The model must return JSON; every question
  then passes the same validation as the curated bank, plus checks that it's
  in the right script and not a duplicate. Valid questions are saved as
  AI-generated and **unreviewed**, so learners never see them until an admin
  marks them reviewed. Invalid ones are listed with the reason.
- **Failure.** Timeouts, errors, bad replies and missing configuration all
  become a friendly "isn't available right now" message and a log entry.
  Practice never depends on AI, so the verified bank is always the fallback.

## Deploying to Render

**Web service**
- Build command: `bash build.sh`
- Start command: `daphne -b 0.0.0.0 -p $PORT config.asgi:application`
- Environment: `DJANGO_SETTINGS_MODULE=config.settings.production`, `SECRET_KEY`,
  `DATABASE_URL`, `REDIS_URL`, `ALLOWED_HOSTS` (Render's own hostname is
  added automatically), optionally `DJANGO_SUPERUSER_USERNAME`,
  `DJANGO_SUPERUSER_EMAIL`, `DJANGO_SUPERUSER_PASSWORD` and the `AI_*` values.

`build.sh` runs every step with the production settings. This matters:
`manage.py` defaults to development settings, and a `collectstatic` run
with those doesn't write the static-files manifest that production needs,
which shows up as "Missing staticfiles manifest entry for 'img/logo.svg'".
The build finishes with `check --deploy`, which fails the build if the
manifest is missing, so the problem can't reach the live site.

`seed_data` is safe on every deploy: reference data is only added once, and
the admin account from `DJANGO_SUPERUSER_*` is created the first time and
left alone after that (its password is only reset with `--update`). Don't
use `createsuperuser --noinput` in the build: it fails with "That username is
already taken" on every deploy after the first.

## Design system

All styling comes from one stylesheet, `static/css/app.css`, built on tokens
defined at the top: colours (deep blue for actions, marigold as a warm
accent, cool neutrals, semantic success/warning/danger), a type scale, radii,
two shadow levels and motion timings. Bootstrap 5 provides layout and
component behaviour; its variables are mapped onto these tokens.

Shared components: buttons (primary, secondary, link), cards, icon badges,
avatars, chips, badges, alerts, form fields, toggle choices, option rows and
the onboarding stepper. Every page is built from these, so the product looks
consistent as it grows. Noto Sans renders English, Bengali and Devanagari with
matching metrics. Icons are Bootstrap Icons, always paired with text or a
screen-reader label.

Rules followed on every page: one primary action per section, generous
spacing, state never shown by colour alone (selected choices also get a
tick), visible keyboard focus, and motion only in response to the user,
apart from one entrance on the landing illustration. Reduced-motion settings
are respected.

## Seed data

```bash
python manage.py seed_data            # safe to run any time
python manage.py seed_data --update   # reset reference rows to seed values
```

It creates the three languages, six proficiency levels, ten difficulty levels
with their XP, six question categories, eight learning goals, the interests
and the three communication modes, then loads any question files in
`apps/practice/seed_questions/`. Re-running creates nothing twice and keeps
admin edits (such as a changed XP value) unless `--update` is passed. Every
question file is validated in full before anything from it is written.

## Environment variables

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Django signing key. Required in production. |
| `DEBUG` | `True` locally. Always `False` in production, whatever this says. |
| `ALLOWED_HOSTS` | Comma-separated hostnames. |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated `https://` origins, if needed. |
| `DATABASE_URL` | `postgres://user:password@host:5432/dbname` |
| `DB_CONN_MAX_AGE` | Seconds to reuse a database connection (default 60). |
| `ADMIN_URL` | Admin path (default `admin/`); change it in production. |
| `TIME_ZONE`, `LOG_LEVEL` | Optional. |
| `EMAIL_*`, `DEFAULT_FROM_EMAIL` | Email delivery; console backend by default. |
| `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS` | Production HTTPS settings. |
| `REDIS_URL`, `AI_API_KEY` | Used from Phase 12 and Phase 14. |

## Testing

```bash
python manage.py test --settings=config.settings.test
```

Tests use PostgreSQL when `DATABASE_URL` is set and in-memory SQLite otherwise.
Run against PostgreSQL before deploying.

Useful checks:

```bash
python manage.py check
python manage.py check --deploy --settings=config.settings.production   # needs production env vars
python manage.py makemigrations --check --dry-run                       # no unapplied model changes
```

## Key design decisions (viva notes)

**Why split settings?** Development, testing and production need different
values. Production never inherits a development default: its secret key,
hosts and database must come from the environment, and `DEBUG` is forced off.

**Why a custom User model from day one?** Django's documentation recommends it.
Swapping the user model after tables exist is a painful migration, so the model
is created now even though its fields come later.

**Why environment variables?** Secrets never enter the code or Git history.
The same code runs locally and on Render with different configuration.

**Why WhiteNoise?** It lets the Django process serve compressed, cache-busted
static files in production without a separate file server.

**Why a health check?** The hosting platform calls `/health/` to know whether
the app and its database are reachable. It returns no internal details.

**Why is the API private by default?** DRF is configured so every endpoint
requires authentication unless a view explicitly opts out, which is safer than
remembering to protect each one.

## Development phases

| Phase | Scope | Status |
|---|---|---|
| 1 | Project foundation | Done |
| 2 | Database architecture and seed-data infrastructure | Done |
| 3 | Authentication and onboarding | Done |
| 4 | Language and profile system | Done |
| 5 | Practice question system | Done |
| 6 | Practice game and XP | Done |
| 7 | Adaptive difficulty | Done |
| 8 | Proficiency estimation | Done |
| 9 | Matching engine | Done |
| 10 | Match discovery UI | Done |
| 11 | Match requests | Done |
| 12 | Real-time exchange | Done |
| 13 | Feedback | Done |
| 14 | AI services | Done |
| 15 | Notifications | |
| 16 | Security hardening | |
| 17 | Testing | |
| 18 | Performance optimisation | |
| 19 | Production configuration | |
| 20 | Deployment and verification | |

Sections on the database design, matching algorithm, XP, adaptive difficulty,
proficiency estimation, AI architecture and deployment are added as each is built.
