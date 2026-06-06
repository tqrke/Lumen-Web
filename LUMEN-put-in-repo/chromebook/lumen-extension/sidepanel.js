const listenBtn = document.getElementById("listen");
const statusEl = document.getElementById("status");
const transcriptEl = document.getElementById("transcript");
const orb = document.getElementById("orb");
const continuousEl = document.getElementById("continuous");

const SpeechRecognition =
  window.SpeechRecognition || window.webkitSpeechRecognition;

let rec = null;
let listening = false;
let restartTimer = null;

function setListening(on) {
  listening = on;
  listenBtn.classList.toggle("listening", on);
  orb.classList.toggle("listening", on);
  listenBtn.textContent = on ? "Listening…" : "Tap to speak";
}

function runCommand(text) {
  const t = (text || "").trim();
  if (!t) return;
  transcriptEl.textContent = t;
  statusEl.textContent = "Processing…";
  chrome.runtime.sendMessage({ type: "lumen:command", text: t }, (res) => {
    if (chrome.runtime.lastError) {
      statusEl.textContent = chrome.runtime.lastError.message;
      return;
    }
    statusEl.textContent = res?.reply || (res?.ok ? "Done." : "Failed.");
    if (continuousEl.checked && res?.ok !== false) {
      restartTimer = setTimeout(() => startListen(), 900);
    }
  });
}

function startListen() {
  if (!rec || listening) return;
  clearTimeout(restartTimer);
  try {
    rec.start();
  } catch {
    rec.stop();
    setTimeout(() => {
      try {
        rec.start();
      } catch (e) {
        statusEl.textContent = `Mic: ${e.message || "unavailable"}`;
      }
    }, 250);
  }
}

if (!SpeechRecognition) {
  statusEl.textContent = "Speech not supported — use Chrome on your Chromebook.";
  listenBtn.disabled = true;
} else {
  rec = new SpeechRecognition();
  rec.lang = "en-GB";
  rec.interimResults = true;
  rec.continuous = false;

  rec.onstart = () => {
    setListening(true);
    statusEl.textContent = "Speak now…";
  };

  rec.onend = () => {
    setListening(false);
  };

  rec.onerror = (e) => {
    setListening(false);
    if (e.error !== "aborted") {
      statusEl.textContent = `Mic: ${e.error} — check Chrome microphone permission.`;
    }
  };

  rec.onresult = (event) => {
    let text = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      text += event.results[i][0].transcript;
    }
    transcriptEl.textContent = text;
    if (event.results[event.results.length - 1].isFinal) {
      runCommand(text);
    }
  };

  listenBtn.addEventListener("click", () => {
    if (listening) {
      rec.stop();
      setListening(false);
      return;
    }
    startListen();
  });
}

document.querySelectorAll(".chip").forEach((btn) => {
  btn.addEventListener("click", () => runCommand(btn.dataset.cmd));
});
