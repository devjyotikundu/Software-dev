#!/usr/bin/env bash
# Render build command:  bash build.sh   (works even if Git lost the executable bit on Windows)
# Every step uses the production settings explicitly. (manage.py defaults to
# development settings, which don't write the static-files manifest that the
# production server needs.)
set -o errexit

SETTINGS=config.settings.production

pip install -r requirements.txt
python manage.py collectstatic --noinput --settings=$SETTINGS
python manage.py migrate --noinput --settings=$SETTINGS
python manage.py seed_data --settings=$SETTINGS       # safe to run on every deploy
# Fails the build (instead of the live site) if anything, e.g. the static
# manifest, is missing.
python manage.py check --deploy --fail-level ERROR --settings=$SETTINGS
