/** AI 问答面板：多轮对话（历史持久化）、选词问、框选截图问。
 *  注意：$ 复用 reader.js 的全局定义，本文件不再声明。 */
const chatState = {
  paperId: state.paperId,
  pendingText: null,   // 选词引用
  pendingImage: null,  // 截图 dataURL
  busy: false,
};

/* ---------- 面板开关 ---------- */
function chatOpen() { $("#chat-panel").classList.add("open"); chatLoad(); }
function chatClose() { $("#chat-panel").classList.remove("open"); }
$("#btn-chat").addEventListener("click", () => {
  $("#chat-panel").classList.contains("open") ? chatClose() : chatOpen();
});
$("#chat-close").addEventListener("click", chatClose);
$("#chat-clear").addEventListener("click", async () => {
  if (!confirm("清空与该文献的全部对话？")) return;
  await API.delete(`/api/v1/papers/${chatState.paperId}/chat/messages`);
  chatLoad();
});

/* ---------- 消息渲染 ---------- */
function chatEscape(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function chatRenderItem(m) {
  const c = m.content || {};
  let html = "";
  if (c.text) html += `<div>${chatEscape(c.text)}</div>`;
  if (c.image) html += `<img src="${c.image}" alt="截图">`;
  return `<div class="chat-msg ${m.role}"><div class="chat-bubble">${html}</div></div>`;
}

async function chatLoad() {
  const list = $("#chat-list");
  try {
    const data = await API.get(`/api/v1/papers/${chatState.paperId}/chat/messages`);
    list.innerHTML = data.items.length
      ? data.items.map(chatRenderItem).join("")
      : `<div class="empty" style="padding:40px 0">向 AI 提问文献内容。<br>选中文字后点「💬 问 AI」，或点顶栏「⛶ 截图问」框选图表提问。</div>`;
    list.scrollTop = list.scrollHeight;
  } catch (e) {
    list.innerHTML = `<div class="empty">${chatEscape(e.message)}</div>`;
  }
}

function chatRenderPending() {
  const box = $("#chat-pending");
  let html = "";
  if (chatState.pendingText) {
    html += `<div class="item"><span style="flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap">📄 引用：${chatEscape(chatState.pendingText)}</span>
      <button class="btn" data-x="text" style="padding:1px 7px">✕</button></div>`;
  }
  if (chatState.pendingImage) {
    html += `<div class="item"><img src="${chatState.pendingImage}"><span style="flex:1">🖼 截图已附加</span>
      <button class="btn" data-x="img" style="padding:1px 7px">✕</button></div>`;
  }
  box.innerHTML = html;
  box.querySelectorAll("[data-x]").forEach((b) => {
    b.addEventListener("click", () => {
      if (b.dataset.x === "text") chatState.pendingText = null;
      else chatState.pendingImage = null;
      chatRenderPending();
    });
  });
}

/* ---------- 发送 ---------- */
async function chatSend() {
  if (chatState.busy) return;
  const input = $("#chat-input");
  const question = input.value.trim();
  if (!question) return;
  let full = question;
  if (chatState.pendingText) {
    full = `【引用文献原文】\n${chatState.pendingText}\n\n【我的问题】\n${question}`;
  }
  chatState.busy = true;
  input.value = "";
  input.disabled = true;
  $("#chat-send").disabled = true;
  $("#chat-list").insertAdjacentHTML("beforeend", `
    <div class="chat-msg user"><div class="chat-bubble">
      ${chatState.pendingText ? `<div class="chat-quote">${chatEscape(chatState.pendingText)}</div>` : ""}
      ${chatState.pendingImage ? `<img src="${chatState.pendingImage}" alt="截图">` : ""}
      <div>${chatEscape(question)}</div>
    </div></div>
    <div class="chat-msg assistant"><div class="chat-bubble chat-typing">AI 思考中…</div></div>`);
  const list = $("#chat-list");
  list.scrollTop = list.scrollHeight;
  const image = chatState.pendingImage;
  chatState.pendingText = null;
  chatState.pendingImage = null;
  chatRenderPending();

  try {
    const reply = await API.post(`/api/v1/papers/${chatState.paperId}/chat`, {
      question: full, image_base64: image,
    });
    list.querySelector(".chat-typing").parentElement.outerHTML = chatRenderItem(reply);
    list.scrollTop = list.scrollHeight;
  } catch (e) {
    list.querySelector(".chat-typing").parentElement.outerHTML =
      `<div class="chat-msg assistant"><div class="chat-bubble" style="color:var(--danger)">${chatEscape(e.message)}</div></div>`;
  } finally {
    chatState.busy = false;
    input.disabled = false;
    $("#chat-send").disabled = false;
    input.focus();
  }
}

$("#chat-send").addEventListener("click", chatSend);
$("#chat-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") chatSend();
});

/* ---------- 选词问（selbar 按钮） ---------- */
$("#sel-ask").addEventListener("click", () => {
  if (!state.currentAnchor) return;
  chatState.pendingText = state.currentAnchor.text;
  window.getSelection().removeAllRanges();
  hideSelbar();
  chatOpen();
  chatRenderPending();
  $("#chat-input").focus();
});

/* ---------- 框选截图问 ---------- */
let shotMode = false, shotStart = null, shotBox = null;

function enterShotMode() {
  shotMode = true;
  document.body.classList.add("shot-mode");
  const tip = document.createElement("div");
  tip.className = "shot-tip";
  tip.textContent = "拖拽框选要问 AI 的图表区域，Esc 取消";
  tip.id = "shot-tip";
  document.body.appendChild(tip);
}

function exitShotMode() {
  shotMode = false;
  shotStart = null;
  document.body.classList.remove("shot-mode");
  $("#shot-tip")?.remove();
  if (shotBox) { shotBox.remove(); shotBox = null; }
}

$("#btn-shot").addEventListener("click", () => { shotMode ? exitShotMode() : enterShotMode(); });
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && shotMode) exitShotMode();
});

document.addEventListener("mousedown", (e) => {
  if (!shotMode) return;
  e.preventDefault();
  shotStart = { x: e.clientX, y: e.clientY };
  shotBox = document.createElement("div");
  shotBox.className = "shot-box";
  shotBox.style.left = `${e.clientX}px`;
  shotBox.style.top = `${e.clientY}px`;
  document.body.appendChild(shotBox);
});

document.addEventListener("mousemove", (e) => {
  if (!shotMode || !shotStart || !shotBox) return;
  const x = Math.min(shotStart.x, e.clientX), y = Math.min(shotStart.y, e.clientY);
  const w = Math.abs(e.clientX - shotStart.x), h = Math.abs(e.clientY - shotStart.y);
  shotBox.style.left = `${x}px`;
  shotBox.style.top = `${y}px`;
  shotBox.style.width = `${w}px`;
  shotBox.style.height = `${h}px`;
});

document.addEventListener("mouseup", (e) => {
  if (!shotMode || !shotStart) return;
  const w = Math.abs(e.clientX - shotStart.x), h = Math.abs(e.clientY - shotStart.y);
  const x = Math.min(shotStart.x, e.clientX), y = Math.min(shotStart.y, e.clientY);
  shotStart = null;
  exitShotMode();
  if (w < 10 || h < 10) { toast("框选区域太小，请重新框选"); return; }
  // 定位框选区域所在页的 page-wrap 与 img
  const cx = x + w / 2, cy = y + h / 2;
  const pageEl = document.elementFromPoint(cx, cy)?.closest?.(".page-wrap");
  if (!pageEl) { toast("请在页面区域内框选"); return; }
  const img = pageEl.querySelector("img.page-img");
  if (!img) { toast("该页未渲染，请稍后重试"); return; }
  const pr = pageEl.getBoundingClientRect();
  const sx = (x - pr.left) / state.zoom, sy = (y - pr.top) / state.zoom;
  const sw = w / state.zoom, sh = h / state.zoom;
  const scale = Math.min(1, 1400 / Math.max(sw, sh));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(sw * scale));
  canvas.height = Math.max(1, Math.round(sh * scale));
  canvas.getContext("2d").drawImage(img, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
  chatState.pendingImage = canvas.toDataURL("image/png");
  chatOpen();
  chatRenderPending();
  $("#chat-input").focus();
});
