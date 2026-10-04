// AI helper forms: ask in the background and show the answer as plain text.
// Without JavaScript the forms post normally and show a result page.
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-ai-form]").forEach((form) => {
    const out = form.querySelector("[data-ai-answer]") || form.parentElement.querySelector("[data-ai-answer]");
    const button = form.querySelector("button[type=submit]");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      button.disabled = true;
      out.hidden = false;
      out.classList.remove("is-error");
      out.textContent = "Thinking…";
      try {
        const response = await fetch(form.action, {
          method: "POST",
          headers: { Accept: "application/json" },
          body: new FormData(form),
          credentials: "same-origin",
        });
        const data = await response.json();
        out.textContent = data.text;               // textContent: never interpreted as HTML
        out.classList.toggle("is-error", !data.ok);
      } catch (_) {
        out.textContent = "The AI helper isn't available right now.";
        out.classList.add("is-error");
      } finally {
        button.disabled = false;
      }
    });
  });
});
