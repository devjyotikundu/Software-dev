"""Helpers shared by each app's seeds.py module."""


def upsert(model, lookup, defaults, *, update):
    """Create a row if missing.

    Existing rows are left alone unless ``update`` is true, so re-running the
    seed command never overwrites values an admin has edited.
    Returns "created", "updated" or "unchanged".
    """
    obj, created = model.objects.get_or_create(**lookup, defaults=defaults)
    if created:
        return "created"
    if update:
        changed = False
        for field, value in defaults.items():
            if getattr(obj, field) != value:
                setattr(obj, field, value)
                changed = True
        if changed:
            obj.save(update_fields=list(defaults))
            return "updated"
    return "unchanged"


def seed_reference(model, rows, *, key, update):
    """Upsert a list of dicts keyed on ``key``. Returns a count per outcome."""
    counts = {"created": 0, "updated": 0, "unchanged": 0}
    for row in rows:
        row = dict(row)
        lookup = {key: row.pop(key)}
        counts[upsert(model, lookup, row, update=update)] += 1
    return counts
