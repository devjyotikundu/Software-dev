# LoopSync — Language Exchange Matcher (Sprint 1)

Team G1-T2 · Project ID G1-09

A small web app with two learner-facing features:
- **Translate** text between languages — no account needed.
- **Learn a language** through short, ordered course lessons, with progress
  saved per user.

## Stack

- **Backend:** Django 5 (Python)
- **Database:** SQLite (file-based, zero setup)
- **Frontend:** Server-rendered HTML/CSS/JS + Bootstrap 5 (CDN)
- **Deployment target:** Render (free tier)

This matches the stack committed to in Lab 4, Exercise A1.

## Run it locally (3 commands, after cloning)

From inside the project folder:

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Then open **http://127.0.0.1:8000/** in your browser.

Optional but recommended — load a couple of demo languages/lessons so the
"Learn" flow has content to show right away:

```bash
python manage.py seed_data
```

To view/edit data directly (users, lessons, progress) create an admin
account and use Django's built-in admin site at `/admin/`:

```bash
python manage.py createsuperuser
```

## Project layout

```
config/         Django project settings & URL routing
accounts/       Registration, login, logout (LEM-01)
learning/       Language, Lesson, LearningProfile, LearningProgress (LEM-02/03/04)
translator/     Public translate page + endpoint (LEM-05)
templates/      Shared base template + home page
static/         CSS and JS
```

## Schema & API contract

The database schema follows the team's Lab 3 ER diagram (`ER_Diagram`):
`User`, `Language`, `LearningProfile`, `Lesson`, `LearningProgress`, and
`VideoCall` (not yet implemented — see "Not yet built" below). The Django
models in `learning/models.py` map onto that diagram field-for-field.

Sprint 1 endpoints (from the Lab 3 API contract / Lab 4 Exercise C2):

| Method + path | Auth required | Purpose |
| --- | --- | --- |
| `POST /auth/register/` | No | Create a user account → 201 |
| `POST /auth/login/` | No | Start a session → 200 / 401 |
| `GET /auth/logout/` | Yes | End the session |
| `POST /learning/profile/` | Yes | Save chosen language + proficiency |
| `GET /learning/next-lesson/` | Yes | Get the next incomplete lesson |
| `POST /learning/progress/` | Yes | Mark a lesson complete |
| `POST /translate/` | No | Translate text (public) |

Every endpoint accepts either a normal HTML form (for the browser pages) or
a JSON body with header `Content-Type: application/json` (for automated
tests / API calls) and responds accordingly.

## Tests

Each app has a `tests.py` with the contract tests from Lab 4, Exercise C2
(one per endpoint, written as Given–When–Then). Run the whole suite with:

```bash
python manage.py test
```

These also run automatically on every push/PR via GitHub Actions
(`.github/workflows/ci.yml`), which installs dependencies, lints with
flake8, and runs `python manage.py test`.

## Branching & Definition of Done

- `main` is always deployable.
- Work happens on short-lived feature branches, merged via reviewed Pull
  Requests.
- Every story must satisfy the team's Definition of Done (Lab 4, Exercise
  B2) before being marked closed.

## Not yet built

- **Video calls (LEM-06)** — matching two learners for a live call is not
  implemented in this pass. The `VideoCall` entity from the ER diagram has
  no corresponding Django model yet; add it as its own app when the team
  is ready to tackle WebRTC.

## Known simplifications

- **CSRF protection is disabled** (`@csrf_exempt`) on the POST endpoints so
  the same view can serve both a plain HTML form and a JSON `fetch()` call
  without extra token plumbing. Fine for a Sprint 1 demo; before any real
  deployment, re-enable CSRF and have the JS read the token from the
  `csrftoken` cookie.
- `POST /learning/profile/` and `POST /learning/progress/` return a **302
  redirect** (not a JSON 401) when called by an unauthenticated *browser*
  request, because `@login_required` redirects by default. API-style JSON
  callers get routed the same way today — tighten this to a plain 401 for
  JSON requests if a stricter contract is needed later.

## Environment variables (for deployment)

| Variable | Purpose | Default |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | Django's cryptographic secret key | insecure dev key |
| `DJANGO_DEBUG` | `True`/`False` | `True` |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hostnames | `*` |

Set real values for these on Render (or wherever the app is deployed) —
never commit a real `SECRET_KEY` to the repository.
