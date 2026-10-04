// Landing page: the word sphere and the scroll story. Loaded only on the landing page.
document.addEventListener("DOMContentLoaded", () => {
  if (!document.querySelector("[data-sphere]")) return;

  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---------------------------------------------------------- word sphere
  const WORDS = [
    ["Hello", "en"], ["नमस्ते", "hi"], ["নমস্কার", "bn"], ["Thank you", "en"], ["धन्यवाद", "hi"], ["ধন্যবাদ", "bn"],
    ["Friend", "en"], ["दोस्त", "hi"], ["বন্ধু", "bn"], ["How are you?", "en"], ["आप कैसे हैं?", "hi"], ["কেমন আছেন?", "bn"],
    ["Tomorrow", "en"], ["कल", "hi"], ["আগামীকাল", "bn"], ["Welcome", "en"], ["स्वागत है", "hi"], ["স্বাগতম", "bn"],
    ["Water", "en"], ["पानी", "hi"], ["জল", "bn"], ["Music", "en"], ["संगीत", "hi"], ["গান", "bn"],
    ["Let's talk", "en"], ["चलो बात करें", "hi"], ["চলো কথা বলি", "bn"], ["See you soon", "en"], ["फिर मिलेंगे", "hi"],
    ["আবার দেখা হবে", "bn"], ["kaise ho?", "hi-Latn"], ["shukriya", "hi-Latn"], ["kemon acho?", "bn-Latn"], ["bhalo achi", "bn-Latn"],
    ["Good morning", "en"], ["सुप्रभात", "hi"], ["সুপ্রভাত", "bn"], ["dost", "hi-Latn"],
    // Greetings and thanks from around the world (shown in grey: not yet practised in the app)
    ["Hola", "es"], ["Gracias", "es"], ["Bonjour", "fr"], ["Merci", "fr"], ["Hallo", "de"], ["Danke", "de"],
    ["Ciao", "it"], ["Grazie", "it"], ["Olá", "pt"], ["Obrigado", "pt"], ["こんにちは", "ja"], ["ありがとう", "ja"],
    ["你好", "zh"], ["谢谢", "zh"], ["안녕하세요", "ko"], ["감사합니다", "ko"], ["مرحبا", "ar"], ["شكرا", "ar"],
    ["Привет", "ru"], ["Спасибо", "ru"], ["Merhaba", "tr"], ["Γεια σου", "el"], ["สวัสดี", "th"], ["שלום", "he"],
    ["Habari", "sw"], ["Halo", "id"], ["Xin chào", "vi"], ["سلام", "fa"], ["வணக்கம்", "ta"], ["నమస్కారం", "te"],
    ["ನಮಸ್ಕಾರ", "kn"], ["നമസ്കാരം", "ml"], ["નમસ્તે", "gu"], ["ਸਤ ਸ੍ਰੀ ਅਕਾਲ", "pa"], ["नमस्कार", "mr"], ["ନମସ୍କାର", "or"],
    ["آداب", "ur"], ["Hoi", "nl"], ["Cześć", "pl"], ["Привіт", "uk"], ["Hej", "sv"], ["ආයුබෝවන්", "si"],
    ["မင်္ဂလာပါ", "my"], ["Sawubona", "zu"], ["Ẹ n lẹ", "yo"], ["Aloha", "haw"],
  ];
  const PRACTISED = new Set(["en", "hi", "bn", "hi-Latn", "bn-Latn"]);
  const sphere = document.querySelector("[data-sphere]");
  const stage = document.querySelector("[data-sphere-stage]");
  const n = WORDS.length;
  const points = WORDS.map(([text, lang], i) => {
    const el = document.createElement("span");
    el.className = "ld-word";
    el.textContent = text;
    el.dataset.lang = lang;
    el.lang = lang;
    el.dir = "auto";                                   // Arabic, Urdu, Persian and Hebrew read right to left
    if (!PRACTISED.has(lang)) el.classList.add("ld-is-world");
    sphere.appendChild(el);
    // Even spread over the sphere (Fibonacci lattice).
    const y = 1 - (i + .5) * 2 / n;
    const r = Math.sqrt(1 - y * y);
    const t = i * Math.PI * (3 - Math.sqrt(5));
    return { el, x: Math.cos(t) * r, y, z: Math.sin(t) * r };
  });

  let ry = 0, rx = -.25, targetX = -.25, spin = .0022, visible = true;
  const radius = () => Math.min(stage.clientWidth, stage.clientHeight) * .46;
  const render = () => {
    const R = radius(), cy = Math.cos(ry), sy = Math.sin(ry), cx = Math.cos(rx), sx = Math.sin(rx);
    for (const p of points) {
      const x1 = p.x * cy + p.z * sy, z1 = -p.x * sy + p.z * cy;      // turn around the vertical axis
      const y2 = p.y * cx - z1 * sx, z2 = p.y * sx + z1 * cx;         // tilt
      const depth = (z2 + 1) / 2;                                      // 0 back … 1 front
      p.el.style.transform = `translate(-50%, -50%) translate3d(${x1 * R}px, ${y2 * R}px, ${z2 * R}px) scale(${.7 + depth * .5})`;
      p.el.style.opacity = (.18 + depth * .82).toFixed(2);
      p.el.style.zIndex = Math.round(depth * 100);
    }
  };
  const loop = () => {
    if (visible) { ry += spin; rx += (targetX - rx) * .05; render(); }
    requestAnimationFrame(loop);
  };
  render();
  if (!reduced) {
    requestAnimationFrame(loop);
    stage.addEventListener("pointermove", (e) => {
      const box = stage.getBoundingClientRect();
      const dx = (e.clientX - box.left) / box.width - .5, dy = (e.clientY - box.top) / box.height - .5;
      spin = .0022 + dx * .012;                 // lean towards the pointer
      targetX = -.25 + dy * .6;
    });
    stage.addEventListener("pointerleave", () => { spin = .0022; targetX = -.25; });
    new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; }).observe(stage);
    document.addEventListener("visibilitychange", () => { visible = !document.hidden; });
  }
  window.addEventListener("resize", render);

  // ---------------------------------------------------------- scroll story
  const device = document.querySelector("[data-device]");
  const steps = [...document.querySelectorAll("[data-step]")];
  // Phones: show each panel under its step instead of the pinned 3D device.
  steps.forEach((step) => {
    const face = document.querySelector(`[data-face="${step.dataset.step}"] .ld-panel`);
    const holder = step.querySelector("[data-clone]");
    if (face && holder) { const copy = face.cloneNode(true); copy.setAttribute("aria-hidden", "true"); holder.appendChild(copy); }
  });
  const activate = (index) => {
    steps.forEach((s, i) => s.classList.toggle("ld-is-active", i === index));
    device.style.setProperty("--turn", index);
  };
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => { if (entry.isIntersecting) activate(Number(entry.target.dataset.step)); });
  }, { rootMargin: "-45% 0px -45% 0px" });
  steps.forEach((s) => observer.observe(s));

  if (!reduced) {
    // A slight tilt of the device as the visitor scrolls, so it feels like a physical object.
    let ticking = false;
    window.addEventListener("scroll", () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        const tilt = Math.sin(window.scrollY / 420) * 5;   // gentle, continuous sway
        device.style.setProperty("--tilt-x", `${tilt}deg`);
        ticking = false;
      });
    }, { passive: true });
  }

});
