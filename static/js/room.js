// Exchange room: live chat over WebSockets, typing hints, and the session timer.
// Without JavaScript (or if the socket can't connect) the forms still work.
document.addEventListener("DOMContentLoaded", () => {
  const root = document.querySelector("[data-room]");
  if (!root) return;

  const userId = Number(root.dataset.userId);
  const list = root.querySelector("[data-messages]");
  const form = root.querySelector("[data-composer]");
  const input = root.querySelector("[data-input]");
  const typing = root.querySelector("[data-typing]");
  const errorBox = root.querySelector("[data-error]");
  const statusEl = root.querySelector("[data-status]");
  const statusText = root.querySelector("[data-status-text]");
  const draftKey = `room-draft-${root.dataset.socketPath}`;

  // Restore a draft saved before a session-change reload.
  try {
    const saved = sessionStorage.getItem(draftKey);
    if (saved) { input.value = saved; sessionStorage.removeItem(draftKey); }
  } catch (_) { /* storage unavailable */ }

  const scrollToEnd = () => { list.scrollTop = list.scrollHeight; };
  scrollToEnd();

  const setStatus = (state, text) => {
    statusEl.dataset.state = state;
    statusText.textContent = text;
  };
  const showError = (text) => {
    errorBox.hidden = false;
    errorBox.textContent = text;
    clearTimeout(showError.timer);
    showError.timer = setTimeout(() => { errorBox.hidden = true; }, 5000);
  };

  // Messages are built with textContent, never innerHTML, so text can't inject markup.
  const addMessage = (m) => {
    if (list.querySelector(`[data-id="${m.id}"]`)) return;
    list.querySelector("[data-empty]")?.remove();
    const li = document.createElement("li");
    li.className = "lx-msg" + (m.sender_id === userId ? " is-mine" : "");
    li.dataset.id = m.id;
    const bubble = document.createElement("div");
    bubble.className = "lx-msg__bubble";
    const body = document.createElement("p");
    body.className = "lx-msg__body";
    body.textContent = m.body;
    const meta = document.createElement("p");
    meta.className = "lx-msg__meta";
    const time = new Date(m.created_at);
    meta.textContent = time.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) +
      (m.language ? `, ${m.language}` : "");
    bubble.append(body, meta);
    li.append(bubble);
    list.append(li);
    scrollToEnd();
    // Let optional add-ons (translation tools) decorate the new message.
    document.dispatchEvent(new CustomEvent("lx:message-added", { detail: { element: li } }));
  };

  // ------------------------------------------------------------ socket
  let socket = null;
  let retry = 0;
  let closedForGood = false;

  const connect = () => {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${scheme}://${location.host}${root.dataset.socketPath}`);
    setStatus("connecting", retry ? "Reconnecting…" : "Connecting…");

    socket.addEventListener("open", () => { retry = 0; setStatus("live", "Live"); });
    socket.addEventListener("message", (event) => {
      let data;
      try { data = JSON.parse(event.data); } catch (_) { return; }
      if (data.type === "message") {
        addMessage(data);
        if (data.sender_id !== userId) typing.hidden = true;
      } else if (data.type === "typing") {
        typing.hidden = false;
        clearTimeout(connect.typingTimer);
        connect.typingTimer = setTimeout(() => { typing.hidden = true; }, 3000);
      } else if (data.type === "session") {
        try { sessionStorage.setItem(draftKey, input.value); } catch (_) { /* ignore */ }
        location.reload();
      } else if (data.type === "error") {
        showError(data.error);
      }
    });
    socket.addEventListener("close", (event) => {
      if (event.code === 4401 || event.code === 4403) {
        closedForGood = true;
        setStatus("closed", "Room closed");
        return;
      }
      if (closedForGood) return;
      setStatus("offline", "Offline, retrying…");
      retry += 1;
      setTimeout(connect, Math.min(10000, 500 * 2 ** retry));
    });
  };
  if ("WebSocket" in window) connect();

  form.addEventListener("submit", (event) => {
    const body = input.value.trim();
    if (!body) { event.preventDefault(); return; }
    if (socket && socket.readyState === WebSocket.OPEN) {
      event.preventDefault();
      socket.send(JSON.stringify({ type: "message", body }));
      input.value = "";
      input.style.height = "";
    }
    // otherwise the normal form post sends it
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });
  let lastTyping = 0;
  input.addEventListener("input", () => {
    input.style.height = "";
    input.style.height = `${Math.min(input.scrollHeight, 160)}px`;
    const now = Date.now();
    if (socket && socket.readyState === WebSocket.OPEN && now - lastTyping > 2000) {
      lastTyping = now;
      socket.send(JSON.stringify({ type: "typing" }));
    }
  });

  // ------------------------------------------------------------- timer
  const timer = root.querySelector("[data-timer]");
  if (timer) {
    const started = new Date(timer.dataset.started).getTime();
    const offset = new Date(timer.dataset.serverNow).getTime() - Date.now(); // align with server clock
    const half = Number(timer.dataset.minutes) * 60;
    const langEl = timer.querySelector("[data-timer-language]");
    const clockEl = timer.querySelector("[data-timer-clock]");
    const barEl = timer.querySelector("[data-timer-bar]");
    const nextEl = timer.querySelector("[data-timer-next]");
    const fmt = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    const tick = () => {
      const elapsed = Math.max(0, Math.floor((Date.now() + offset - started) / 1000));
      if (elapsed < half) {
        langEl.textContent = timer.dataset.first;
        clockEl.textContent = `${fmt(half - elapsed)} left`;
        barEl.style.width = `${(elapsed / half) * 100}%`;
        nextEl.textContent = `Then ${timer.dataset.second} for ${timer.dataset.minutes} minutes.`;
      } else if (elapsed < 2 * half) {
        langEl.textContent = timer.dataset.second;
        clockEl.textContent = `${fmt(2 * half - elapsed)} left`;
        barEl.style.width = `${((elapsed - half) / half) * 100}%`;
        nextEl.textContent = "Last part of the session.";
      } else {
        langEl.textContent = "Time's up";
        clockEl.textContent = "Great work, both of you";
        barEl.style.width = "100%";
        nextEl.textContent = "Carry on in either language, or end the session.";
      }
    };
    tick();
    setInterval(tick, 1000);
  }

  // ---------------------------------------------------- starters
  const starters = root.querySelector("[data-starters]");
  const nextStarter = root.querySelector("[data-next-starter]");
  if (starters && nextStarter && starters.children.length > 1) {
    nextStarter.hidden = false;
    let index = 0;
    nextStarter.addEventListener("click", () => {
      starters.children[index].hidden = true;
      index = (index + 1) % starters.children.length;
      starters.children[index].hidden = false;
    });
  }
});
