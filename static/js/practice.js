// Keyboard shortcuts on the question page: A–D or 1–4 choose an option.
// The form works without this; it only adds speed for keyboard users.
document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("[data-quiz-form]");
  if (!form) return;
  const keys = { a: "A", b: "B", c: "C", d: "D", 1: "A", 2: "B", 3: "C", 4: "D" };
  document.addEventListener("keydown", (event) => {
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.target.matches("input[type=text], textarea")) return;
    const letter = keys[event.key.toLowerCase()];
    if (!letter) return;
    const radio = form.querySelector(`input[name="option"][value="${letter}"]`);
    if (radio) {
      radio.checked = true;
      radio.focus();
    }
  });
});
