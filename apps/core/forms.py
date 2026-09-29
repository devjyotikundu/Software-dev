class BootstrapFormMixin:
    """Adds Bootstrap classes and accessible error attributes to widgets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            kind = getattr(widget, "input_type", None)
            if kind in ("checkbox", "radio"):
                continue  # rendered as toggle buttons by templates/partials/_field.html
            css = "form-select" if kind == "select" else "form-control"
            widget.attrs["class"] = f"{widget.attrs.get('class', '')} {css}".strip()

    def full_clean(self):
        super().full_clean()
        for name in self.errors:
            if name in self.fields:
                attrs = self.fields[name].widget.attrs
                attrs["aria-invalid"] = "true"
                attrs["aria-describedby"] = f"{self[name].auto_id}_error"
                if "class" in attrs:
                    attrs["class"] += " is-invalid"
