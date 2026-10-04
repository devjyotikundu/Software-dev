// Availability editor: "Add another time" clones a hidden row template.
// Without JavaScript the page still works with the one blank row Django renders.
document.addEventListener("DOMContentLoaded", () => {
  const list = document.querySelector("[data-slot-list]");
  const template = document.querySelector("[data-slot-template]");
  const addButton = document.querySelector("[data-slot-add]");
  const total = document.querySelector('input[name="slots-TOTAL_FORMS"]');
  const max = document.querySelector('input[name="slots-MAX_NUM_FORMS"]');
  if (!list || !template || !addButton || !total) return;

  const refresh = () => {
    addButton.disabled = max && Number(total.value) >= Number(max.value);
  };

  addButton.hidden = false;
  addButton.addEventListener("click", () => {
    const index = Number(total.value);
    const html = template.innerHTML.replace(/__prefix__/g, String(index));
    list.insertAdjacentHTML("beforeend", html);
    total.value = String(index + 1);
    const row = list.lastElementChild;
    row.classList.add("is-new");
    row.querySelector("select")?.focus();
    refresh();
  });

  // Rows marked for removal fade so the change is visible before saving.
  list.addEventListener("change", (event) => {
    if (event.target.matches("[data-slot-delete]")) {
      event.target.closest("[data-slot]").classList.toggle("is-removed", event.target.checked);
    }
  });
  list.querySelectorAll("[data-slot-delete]:checked").forEach((box) =>
    box.closest("[data-slot]").classList.add("is-removed"));
  refresh();
});
