// Preselect the browser's time zone when the user hasn't chosen one yet.
document.addEventListener("DOMContentLoaded", () => {
  const select = document.querySelector("select[data-detect-timezone]");
  if (!select || select.value !== "UTC") return;
  try {
    const detected = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (detected && [...select.options].some((o) => o.value === detected)) {
      select.value = detected;
    }
  } catch (_) {
    // Older browsers: keep the current value.
  }
});
