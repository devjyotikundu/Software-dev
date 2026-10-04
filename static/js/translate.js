// In-chat translation, romanization, listening (text-to-speech) and speaking
// (speech-to-text). Optional: the chat works exactly the same without it.
// Translations are fetched on request and shown under the original, which
// always stays visible. Nothing here changes or stores the original message.
document.addEventListener("DOMContentLoaded", () => {
  const root = document.querySelector("[data-room]");
  if (!root) return;

  const NAMES = { en: "English", hi: "Hindi", bn: "Bengali" };
  const LOCALES = { en: "en-IN", hi: "hi-IN", bn: "bn-IN" };
  const DEVANAGARI = /[\u0900-\u097F]/;
  const BENGALI = /[\u0980-\u09FF]/;
  const aiOn = root.dataset.translateEnabled === "1";
  const languages = (root.dataset.languages || "").split(",").filter((c) => NAMES[c]);
  const csrf = root.querySelector("input[name=csrfmiddlewaretoken]")?.value || "";
  const statusEl = root.querySelector("[data-tr-status]");
  const STORE = "lx-chat-translation";

  // ------------------------------------------------------------ settings
  const defaults = {
    target: languages.includes(root.dataset.myLanguage) ? root.dataset.myLanguage : languages[0] || "en",
    format: "native", auto: false, learning: false,
    speech: languages.find((c) => c !== root.dataset.myLanguage) || languages[0] || "en",
  };
  let settings = { ...defaults };
  try { settings = { ...defaults, ...JSON.parse(localStorage.getItem(STORE) || "{}") }; } catch (_) { /* private mode */ }
  const save = () => { try { localStorage.setItem(STORE, JSON.stringify(settings)); } catch (_) { /* ignore */ } };

  const say = (text) => {
    statusEl.hidden = false;
    statusEl.textContent = text;
    clearTimeout(say.timer);
    say.timer = setTimeout(() => { statusEl.hidden = true; }, 4000);
  };

  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const iconButton = (icon, label, extraClass = "") => {
    const b = el("button", `lx-msg-tool ${extraClass}`.trim());
    b.type = "button";
    const i = el("i", `bi ${icon}`); i.setAttribute("aria-hidden", "true");
    b.append(i, el("span", "lx-msg-tool__label", label));
    return b;
  };
  const optionsFor = () => {
    const list = [];
    languages.forEach((code) => {
      list.push({ target: code, format: "native", label: `To ${NAMES[code]}` });
      if (code !== "en") list.push({ target: code, format: "roman", label: `To ${NAMES[code]} (Roman letters)` });
    });
    return list;
  };

  // ------------------------------------------------------- listen (TTS)
  const speak = (text, locale) => {
    if (!("speechSynthesis" in window)) { say("Listening isn't supported in this browser."); return; }
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = locale;
    const voices = window.speechSynthesis.getVoices();
    const want = locale.toLowerCase();
    const voice = voices.find((v) => v.lang.toLowerCase().replace("_", "-") === want)
      || voices.find((v) => v.lang.toLowerCase().startsWith(want.split("-")[0]));
    if (voice) utterance.voice = voice;            // otherwise the browser's default voice
    utterance.onerror = () => say("Couldn't play the audio. The chat still works as normal.");
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
  };
  const localeOf = (text) => (DEVANAGARI.test(text) ? "hi-IN" : BENGALI.test(text) ? "bn-IN" : "en-IN");

  // ------------------------------------------------------------ requests
  const post = async (url, data) => {
    const response = await fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "X-CSRFToken": csrf, Accept: "application/json" },
      body: new URLSearchParams(data),
    });
    let body = {};
    try { body = await response.json(); } catch (_) { /* non-JSON error page */ }
    if (!response.ok || !body.ok) throw new Error(body.error || "Translation unavailable. Try again.");
    return body;
  };
  const urlFor = (template, id) => template.replace(/\/0\/(translate|romanize)\/$/, `/${id}/$1/`);

  // --------------------------------------------------------------- panels
  const panelFor = (bubble) => {
    let panel = bubble.querySelector(".lx-tr");
    if (!panel) { panel = el("div", "lx-tr"); bubble.insertBefore(panel, bubble.querySelector(".lx-msg__meta")); }
    panel.replaceChildren();
    panel.hidden = false;
    return panel;
  };
  const panelActions = (panel, text, locale) => {
    const row = el("div", "lx-tr__actions");
    if (text) {
      const listen = iconButton("bi-volume-up", "Listen");
      listen.addEventListener("click", () => speak(text, locale));
      row.append(listen);
    }
    const hide = iconButton("bi-x-lg", "Hide");
    hide.addEventListener("click", () => { panel.hidden = true; });
    row.append(hide);
    panel.append(row);
  };

  const showTranslation = async (li, option, { quiet = false } = {}) => {
    const bubble = li.querySelector(".lx-msg__bubble");
    const original = li.querySelector(".lx-msg__body").textContent.trim();
    const panel = panelFor(bubble);
    panel.append(el("p", "lx-tr__label", "Translating…"));
    try {
      const data = await post(urlFor(root.dataset.translateUrl, li.dataset.id),
        { target: option.target, format: option.format });
      if (quiet && data.translation.trim().toLowerCase() === original.toLowerCase()) {
        panel.hidden = true;                      // already in that language: nothing to add
        return;
      }
      panel.replaceChildren();
      panel.append(el("p", "lx-tr__label", `${data.target_name}${data.format === "roman" ? " (Roman letters)" : ""}`));
      const text = el("p", "lx-tr__text", data.translation);
      if (data.format === "native") text.lang = data.target;
      panel.append(text);
      if (settings.learning) {
        if (data.original_romanized) panel.append(el("p", "lx-tr__extra", `Original in Roman letters: ${data.original_romanized}`));
        if (data.translation_romanized) panel.append(el("p", "lx-tr__extra", `Roman letters: ${data.translation_romanized}`));
      }
      panelActions(panel, data.translation, data.format === "roman" ? "en-IN" : data.locale);
    } catch (error) {
      panel.replaceChildren(el("p", "lx-tr__error", error.message));
      const retry = iconButton("bi-arrow-repeat", "Try again");
      retry.addEventListener("click", () => showTranslation(li, option));
      panel.append(retry);
      panelActions(panel, "", "");
    }
  };

  const showRomanized = async (li) => {
    const panel = panelFor(li.querySelector(".lx-msg__bubble"));
    try {
      const data = await post(urlFor(root.dataset.romanizeUrl, li.dataset.id), {});
      panel.append(el("p", "lx-tr__label", "Romanized (same language, Latin letters)"));
      panel.append(el("p", "lx-tr__text", data.romanized));
      panelActions(panel, "", "");
    } catch (error) {
      panel.append(el("p", "lx-tr__error", error.message));
      panelActions(panel, "", "");
    }
  };

  // ---------------------------------------------------- per-message tools
  let openMenu = null;
  const closeMenu = () => { if (openMenu) { openMenu.hidden = true; openMenu.previousElementSibling?.setAttribute("aria-expanded", "false"); openMenu = null; } };
  document.addEventListener("click", (event) => { if (openMenu && !openMenu.parentElement.contains(event.target)) closeMenu(); });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeMenu(); });

  const decorate = (li) => {
    if (!li?.dataset?.id || li.dataset.trReady) return;
    li.dataset.trReady = "1";
    const bubble = li.querySelector(".lx-msg__bubble");
    const original = li.querySelector(".lx-msg__body")?.textContent.trim() || "";
    const tools = el("div", "lx-msg__tools");

    if (aiOn && languages.length) {
      const wrap = el("div", "lx-msg-menu");
      const toggle = iconButton("bi-translate", "Translate");
      toggle.setAttribute("aria-haspopup", "true");
      toggle.setAttribute("aria-expanded", "false");
      const menu = el("div", "lx-msg-menu__list");
      menu.hidden = true;
      optionsFor().forEach((option) => {
        const item = el("button", "lx-msg-menu__item", option.label);
        item.type = "button";
        item.addEventListener("click", () => { closeMenu(); showTranslation(li, option); });
        menu.append(item);
      });
      toggle.addEventListener("click", () => {
        const opening = menu.hidden;
        closeMenu();
        if (opening) { menu.hidden = false; toggle.setAttribute("aria-expanded", "true"); openMenu = menu; menu.firstChild?.focus(); }
      });
      wrap.append(toggle, menu);
      tools.append(wrap);
    }
    if (DEVANAGARI.test(original) || BENGALI.test(original)) {
      const roman = iconButton("bi-alphabet", "Romanize");
      roman.addEventListener("click", () => showRomanized(li));
      tools.append(roman);
    }
    const listen = iconButton("bi-volume-up", "Listen");
    listen.addEventListener("click", () => speak(original, localeOf(original)));
    tools.append(listen);
    bubble.append(tools);

    if (aiOn && settings.auto && li.dataset.autoEligible === "1" && !li.classList.contains("is-mine")) {
      showTranslation(li, { target: settings.target, format: settings.format }, { quiet: true });
    }
  };

  const list = root.querySelector("[data-messages]");
  const existing = [...list.querySelectorAll(".lx-msg")];
  existing.slice(-10).forEach((li) => { li.dataset.autoEligible = "1"; });   // auto-translate only recent history
  existing.forEach(decorate);
  document.addEventListener("lx:message-added", (event) => {
    event.detail.element.dataset.autoEligible = "1";
    decorate(event.detail.element);
  });

  // -------------------------------------------------------- settings UI
  const panel = root.querySelector("[data-tr-settings]");
  const toggle = root.querySelector("[data-tr-settings-toggle]");
  const targetSelect = root.querySelector("[data-tr-target]");
  const speechSelect = root.querySelector("[data-tr-speech-lang]");
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  optionsFor().forEach((option) => {
    const o = el("option", "", option.label.replace(/^To /, ""));
    o.value = `${option.target}|${option.format}`;
    targetSelect.append(o);
  });
  targetSelect.value = `${settings.target}|${settings.format}`;
  targetSelect.addEventListener("change", () => {
    [settings.target, settings.format] = targetSelect.value.split("|");
    save();
  });
  languages.forEach((code) => { const o = el("option", "", NAMES[code]); o.value = code; speechSelect.append(o); });
  speechSelect.value = settings.speech;
  speechSelect.addEventListener("change", () => { settings.speech = speechSelect.value; save(); });
  root.querySelector("[data-tr-auto]").checked = settings.auto;
  root.querySelector("[data-tr-auto]").addEventListener("change", (e) => { settings.auto = e.target.checked; save(); });
  root.querySelector("[data-tr-learning]").checked = settings.learning;
  root.querySelector("[data-tr-learning]").addEventListener("change", (e) => { settings.learning = e.target.checked; save(); });
  if (!aiOn) panel.querySelectorAll("[data-tr-ai-only]").forEach((n) => n.remove());
  if (!SpeechRecognition) panel.querySelectorAll("[data-tr-speech-only]").forEach((n) => n.remove());

  toggle.hidden = false;
  toggle.addEventListener("click", () => {
    panel.hidden = !panel.hidden;
    toggle.setAttribute("aria-expanded", String(!panel.hidden));
  });

  // ------------------------------------------------- speak (speech input)
  const mic = root.querySelector("[data-tr-mic]");
  const input = root.querySelector("[data-input]");
  if (SpeechRecognition && mic && input) {
    mic.hidden = false;
    let recognition = null;
    mic.addEventListener("click", () => {
      if (recognition) { recognition.stop(); return; }
      recognition = new SpeechRecognition();
      recognition.lang = LOCALES[settings.speech] || "en-IN";
      recognition.interimResults = false;
      recognition.onresult = (event) => {
        const heard = [...event.results].map((r) => r[0].transcript).join(" ").trim();
        if (heard) {
          input.value = input.value ? `${input.value.trimEnd()} ${heard}` : heard;
          input.dispatchEvent(new Event("input"));
          input.focus();
        }
      };
      recognition.onerror = () => say("Couldn't hear that. You can keep typing as normal.");
      recognition.onend = () => { recognition = null; mic.setAttribute("aria-pressed", "false"); mic.classList.remove("is-listening"); };
      mic.setAttribute("aria-pressed", "true");
      mic.classList.add("is-listening");
      recognition.start();
    });
  }
});
