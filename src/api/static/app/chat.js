// chat.js — the floating chat assistant, carried over unchanged in
// behavior from the previous single-page console (POST /chat, a real,
// grounded Q&A over a specific run -- see src/services/chat_assistant.py).
// Only addition for the multi-page shell: pages set which run the chat
// should answer about via setChatContext(runId, label), since "the loaded
// report" is no longer a single global page state.
"use strict";

let _chatRunId = null;
let _chatContextLabel = null;

function setChatContext(runId, label) {
  _chatRunId = runId || null;
  _chatContextLabel = label || null;
  const titleEl = document.getElementById("chatPanelTitle");
  if (titleEl) titleEl.textContent = _chatContextLabel ? (t("askAboutBriefing") + " — " + _chatContextLabel) : t("askAboutBriefing");
}

(function initChat() {
  const chatFabEl = document.getElementById("chatFab");
  const chatPanelEl = document.getElementById("chatPanel");
  const chatCloseBtnEl = document.getElementById("chatCloseBtn");
  const chatMessagesEl = document.getElementById("chatMessages");
  const chatFormEl = document.getElementById("chatForm");
  const chatInputEl = document.getElementById("chatInput");
  const chatSubmitBtnEl = document.getElementById("chatSubmitBtn");
  if (!chatFabEl || !chatPanelEl || !chatFormEl) return;

  let chatHistory = [];
  let chatGreeted = false;

  function appendChatBubble(cssClass, text, sources) {
    const bubble = document.createElement("div");
    bubble.className = "chat-bubble " + cssClass;
    bubble.textContent = text;
    if (sources && sources.length) {
      const srcEl = document.createElement("span");
      srcEl.className = "chat-sources";
      srcEl.textContent = t("groundedIn") + " " + sources.join("; ");
      bubble.appendChild(srcEl);
    }
    chatMessagesEl.appendChild(bubble);
    chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
    return bubble;
  }

  function openChat() {
    chatPanelEl.hidden = false;
    chatFabEl.setAttribute("aria-expanded", "true");
    if (!chatGreeted) {
      appendChatBubble("assistant", t("chatGreeting"));
      chatGreeted = true;
    }
    chatInputEl.focus();
  }
  function closeChat() {
    chatPanelEl.hidden = true;
    chatFabEl.setAttribute("aria-expanded", "false");
  }

  chatFabEl.addEventListener("click", function () {
    if (chatPanelEl.hidden) openChat(); else closeChat();
  });
  chatCloseBtnEl.addEventListener("click", closeChat);

  chatFormEl.addEventListener("submit", function (evt) {
    evt.preventDefault();
    const message = chatInputEl.value.trim();
    if (!message) return;
    appendChatBubble("user", message);
    const historyForRequest = chatHistory.slice();
    chatHistory.push({ role: "user", text: message });
    chatInputEl.value = "";
    chatInputEl.disabled = true;
    chatSubmitBtnEl.disabled = true;
    const thinkingBubble = appendChatBubble("assistant thinking", t("chatThinking"));

    api.chat(message, _chatRunId, historyForRequest, getLang())
      .then(function (body) {
        thinkingBubble.remove();
        appendChatBubble("assistant", body.answer, body.sources);
        chatHistory.push({ role: "assistant", text: body.answer });
      })
      .catch(function (err) {
        thinkingBubble.remove();
        appendChatBubble("assistant", t("chatError", err.message));
      })
      .finally(function () {
        chatInputEl.disabled = false;
        chatSubmitBtnEl.disabled = false;
        chatInputEl.focus();
      });
  });
})();
