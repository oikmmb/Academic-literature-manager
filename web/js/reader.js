/** 阅读器核心：页渲染 + 词级文本层 + 选区锚定 + 高亮 + 笔记 + 自动保存。
 *  锚点 = {paper_id, page, word_start, word_end, char_start, char_end}，重渲染 100% 稳定。 */
const $ = (sel) => document.querySelector(sel);
const K = 150 / 72;   // PDF 点 → 渲染像素（RENDER_DPI=150）
const CJK = /[一-鿿]/;

const state = {
  paperId: +new URLSearchParams(location.search).get("id"),
  paper: null,
  doc: { kind: "main", suppId: 0, label: "" },   // 当前文档上下文
  supplements: [],   // 补充材料列表
  pageCount: 0,
  zoom: 1,
  words: new Map(),        // page -> words 数组
  pageNat: new Map(),      // page -> 页面自然尺寸 {w,h}（渲染像素，meta 时填充）
  pageRendered: new Set(), // 内容已渲染的页
  pageInFlight: new Set(), // 渲染请求进行中的页
  anns: new Map(),         // id -> ann
  currentAnchor: null,
  highlightOpacity: 0.55,  // 新创建高亮的默认透明度
  multiSegs: [],           // 多段选区 [{page, ws, we}]（普通拖选 + Shift 拖选累积）
  shiftDragging: null,     // Shift 拖动进行中 {page, wi, lastPage, lastWi}
  shiftHintShown: false,
  currentPage: 1,
  currentDpi: 150,         // 当前渲染清晰度档位（随缩放自动升级 150→300→600）
  offsetTop: new Map(),    // page -> offsetTop 缓存
  pageH: new Map(),        // page -> 渲染高度
};

/* ================= 自动保存（800ms 防抖 + 退出 flush + 崩溃 keepalive） ================= */
const pending = { upserts: new Map(), deletes: new Set() };
let flushTimer = null;

function queueUpsert(ann) { pending.upserts.set(ann.id, ann); pending.deletes.delete(ann.id); scheduleFlush(); }
function queueDelete(id) { pending.upserts.delete(id); pending.deletes.add(id); scheduleFlush(); }
function scheduleFlush() { clearTimeout(flushTimer); flushTimer = setTimeout(flush, 800); }

// 前端 ann 对象用 id 键，后端协议字段为 client_id
function buildPayload() {
  return {
    upserts: [...pending.upserts.values()].map(({ id, ...rest }) => ({ client_id: id, ...rest })),
    deletes: [...pending.deletes],
  };
}

async function flush() {
  clearTimeout(flushTimer);
  if (!pending.upserts.size && !pending.deletes.size) return true;
  const payload = buildPayload();
  pending.upserts.clear();
  pending.deletes.clear();
  try {
    await API.post("/api/v1/annotations/batch", payload);
    return true;
  } catch (e) {
    // 回填时恢复前端内部键名（id），下次 flush 重新映射为 client_id
    for (const u of payload.upserts) {
      const { client_id, ...rest } = u;
      pending.upserts.set(client_id, { id: client_id, ...rest });
    }
    for (const d of payload.deletes) pending.deletes.add(d);
    toast("保存失败，将自动重试");
    return false;
  }
}

// 崩溃兜底：窗口直接关闭时用同步 XHR 保证请求发出（beforeunload 中同步请求阻塞关闭，
// 比 keepalive fetch 更可靠 —— WebView2 进程退出时 keepalive 可能被中断）
window.addEventListener("beforeunload", () => {
  if (!pending.upserts.size && !pending.deletes.size) return;
  try {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/v1/annotations/batch", false);   // 同步模式
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.send(JSON.stringify(buildPayload()));
  } catch (e) { /* 最后机会失败：800ms 防抖已保存绝大部分修改 */ }
});

/* ================= 文档上下文（正文 / 补充材料） ================= */
function docParam() {
  return state.doc.suppId ? `supp:${state.doc.suppId}` : "main";
}

/* 阅读器内添加补充材料（导入后随时可加） */
$("#btn-add-supp").addEventListener("click", () => $("#supp-input").click());
$("#supp-input").addEventListener("change", async (e) => {
  const files = [...e.target.files];
  e.target.value = "";
  for (const f of files) {
    if (!f.name.toLowerCase().endsWith(".pdf")) { toast("仅支持 PDF 文件"); continue; }
    try {
      const fd = new FormData();
      fd.append("file", f);
      await API.upload(`/api/v1/papers/${state.paperId}/supplements`, fd);
      toast(`已添加补充材料：${f.name}`);
    } catch (err) { toast(err.message); }
  }
  const res = await API.get(`/api/v1/papers/${state.paperId}/supplements`);
  state.supplements = res.items;
  renderDocBar();
});

function renderDocBar() {
  const bar = $("#doc-bar");
  bar.style.display = "block";   // 始终显示：无补充材料时也保留「＋」添加入口
  let html = `<button class="doc-item ${state.doc.suppId === 0 ? "active" : ""}" data-supp="0">
       📄 正文<span class="pages">${state.paper.pdf_pages}页</span>
     </button>`;
  if (state.supplements.length) {
    html += state.supplements.map((s) => `
      <button class="doc-item ${state.doc.suppId === s.id ? "active" : ""}" data-supp="${s.id}">
        📎 <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(s.label)}</span>
        <span class="pages">${s.pdf_pages}页</span>
        <span class="doc-del" data-del="${s.id}" title="删除该补充材料">✕</span>
      </button>`).join("");
  } else {
    html += `<div style="font-size:12px; color:var(--text-2); padding:8px 10px; line-height:1.6">
      尚无补充材料<br>点右上「＋」添加 SI / 附录 PDF</div>`;
  }
  $("#doc-list").innerHTML = html;
  $("#doc-list").querySelectorAll(".doc-item").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      if (e.target.closest(".doc-del")) return;   // 删除按钮不触发切换
      switchDoc(+btn.dataset.supp);
    });
  });
  $("#doc-list").querySelectorAll(".doc-del").forEach((del) => {
    del.addEventListener("click", async (e) => {
      e.stopPropagation();
      const supp = state.supplements.find((s) => s.id === +del.dataset.del);
      if (!confirm(`确定删除补充材料「${supp?.label}」？其批注将一并删除。`)) return;
      try {
        await API.delete(`/api/v1/supplements/${del.dataset.del}`);
        // 若正在查看被删的补充材料，切回正文
        if (state.doc.suppId === +del.dataset.del) await switchDoc(0);
        state.supplements = state.supplements.filter((s) => s.id !== +del.dataset.del);
        renderDocBar();
        toast("已删除");
      } catch (err) { toast(err.message); }
    });
  });
}

async function switchDoc(suppId) {
  if (state.doc.suppId === suppId) return;   // 重复点击当前文档不重载
  await flush();   // 切换前确保批注落盘
  const supp = state.supplements.find((s) => s.id === suppId);
  state.doc = supp
    ? { kind: "supp", suppId: supp.id, label: supp.label }
    : { kind: "main", suppId: 0, label: "" };
  // 重置文档级状态
  state.words.clear();
  state.pageNat.clear();
  state.pageRendered.clear();
  state.pageInFlight.clear();
  state.offsetTop.clear();
  state.pageH.clear();
  state.anns.clear();
  state.currentPage = 1;
  $("#pages").innerHTML = "";
  $("#reader-wrap").scrollTop = 0;

  state.pageCount = supp ? supp.pdf_pages : (state.paper.pdf_pages || 1);
  $("#paper-title").textContent = supp ? supp.label : state.paper.title;
  $("#page-ind").textContent = `第 1 / ${state.pageCount} 页`;
  renderDocBar();

  const res = await API.get(`/api/v1/papers/${state.paperId}/annotations?supp_id=${state.doc.suppId}`);
  for (const a of res.items) state.anns.set(a.id, a);
  renderNotesList();
  updateNotesCount();

  const meta = await API.get(`/api/v1/papers/${state.paperId}/pages/meta?doc=${docParam()}`);
  createPlaceholders(meta.pages);
  await ensurePage(1);
  fitWidth();
}

/* ================= 页面渲染 =================
 * 初始化时按 meta 创建全部占位容器（滚动条/offsetTop 正确），
 * 可视区 ±1 视口按需渲染内容；离远时清空内容保留占位（滚动不跳动）。 */
function createPlaceholders(pages) {
  for (const p of pages) {
    const nat = { w: p.w * K, h: p.h * K };
    state.pageNat.set(p.page, nat);
    const wrap = document.createElement("div");
    wrap.className = "page-wrap";
    wrap.dataset.page = p.page;
    wrap.style.width = `${nat.w * state.zoom}px`;
    wrap.style.height = `${nat.h * state.zoom}px`;
    wrap.style.background = "#fff";
    $("#pages").appendChild(wrap);
    state.pageH.set(p.page, nat.h * state.zoom);
  }
}

async function ensurePage(n) {
  if (state.pageRendered.has(n) || state.pageInFlight.has(n)) return;
  state.pageInFlight.add(n);
  try {
    const data = await API.get(`/api/v1/papers/${state.paperId}/pages/${n}/words?doc=${docParam()}`);
    state.words.set(n, data.words);
    state.pageRendered.add(n);
    buildPageDom(n, data);
  } finally {
    state.pageInFlight.delete(n);
  }
}

function buildPageDom(n, data) {
  const wrap = document.querySelector(`.page-wrap[data-page="${n}"]`);
  if (!wrap) return;
  const nat = { w: data.size.w * K, h: data.size.h * K };
  state.pageNat.set(n, nat);
  wrap.innerHTML = "";
  wrap.style.width = `${nat.w * state.zoom}px`;
  wrap.style.height = `${nat.h * state.zoom}px`;

  const inner = document.createElement("div");
  inner.className = "page-inner";
  inner.style.width = `${nat.w}px`;
  inner.style.height = `${nat.h}px`;
  inner.style.transform = `scale(${state.zoom})`;

  const img = document.createElement("img");
  img.className = "page-img";
  img.src = `/api/v1/papers/${state.paperId}/pages/${n}/image?doc=${docParam()}&dpi=${state.currentDpi}`;
  img.style.width = `${nat.w}px`;
  img.style.height = `${nat.h}px`;

  const textlayer = document.createElement("div");
  textlayer.className = "textlayer";
  for (const w of data.words) {
    const span = document.createElement("span");
    span.dataset.i = w.i;
    span.dataset.zone = w.zone || "body";   // 页眉页脚词不可选（CSS user-select:none）
    // 英文词后带真实空格：浏览器双击才只选一个词（无空格时相邻词会被当作同一"单词"连选）
    span.textContent = CJK.test(w.t) ? w.t : `${w.t} `;
    span.style.left = `${w.x * K}px`;
    span.style.top = `${w.y * K}px`;
    span.style.width = `${w.w * K}px`;
    span.style.height = `${w.h * K}px`;
    span.style.fontSize = `${w.h * K}px`;
    textlayer.appendChild(span);
  }

  const hllayer = document.createElement("div");
  hllayer.className = "hllayer";

  inner.append(img, textlayer, hllayer);
  wrap.append(inner);
  const pagenum = document.createElement("div");
  pagenum.className = "page-num";
  pagenum.textContent = `${n} / ${state.pageCount}`;
  wrap.appendChild(pagenum);

  // 扫描版提示
  if (!data.words.length) {
    const tip = document.createElement("div");
    tip.className = "scan-tip";
    tip.innerHTML = `该页无可选文本（扫描版）<button class="btn" data-page-note="${n}">添加页级笔记</button>`;
    wrap.appendChild(tip);
  }

  state.offsetTop.delete(n);
  state.pageH.set(n, nat.h * state.zoom);
  drawPageAnns(n);
}

function unloadPage(n) {
  // 只清内容保留占位容器，滚动位置与滚动条稳定
  if (!state.pageRendered.has(n)) return;
  const el = document.querySelector(`.page-wrap[data-page="${n}"]`);
  if (el) el.innerHTML = "";
  state.pageRendered.delete(n);
}

function pageOffset(n) {
  if (state.offsetTop.has(n)) return state.offsetTop.get(n);
  const el = document.querySelector(`.page-wrap[data-page="${n}"]`);
  if (!el) return null;
  const off = el.offsetTop;
  state.offsetTop.set(n, off);
  return off;
}

function lazyRender() {
  const wrap = $("#reader-wrap");
  const vh = wrap.clientHeight;
  const top = wrap.scrollTop, bottom = top + vh;
  for (let n = 1; n <= state.pageCount; n++) {
    const off = pageOffset(n);
    if (off === null) continue;
    const h = state.pageH.get(n) || vh;
    if (off < bottom + vh && off + h > top - vh) ensurePage(n);
    else unloadPage(n);
  }
  // 当前页指示
  let cur = 1, best = Infinity;
  for (const el of document.querySelectorAll(".page-wrap")) {
    const d = Math.abs(el.offsetTop - top);
    if (d < best) { best = d; cur = +el.dataset.page; }
  }
  if (cur !== state.currentPage) { state.currentPage = cur; $("#page-ind").textContent = `第 ${cur} / ${state.pageCount} 页`; }
}

/* ================= 选区锚定（坐标反推 + 整词吸附） =================
 * 不用 DOM 节点回溯（从词间空隙/行间起划会找不到锚点），而是取选区
 * 首尾视觉矩形中心点反推最近词，并按完整词吸附 —— 划词范围与显示内容
 * 始终一致，跨行由 getClientRects 的顺序保证。 */
function smartJoin(texts) {
  let out = "";
  for (const t of texts) {
    if (!out) { out = t; continue; }
    out += (CJK.test(out.at(-1)) && CJK.test(t[0])) ? "" : " " + t;
  }
  return out;
}

function pagePointFromClient(pageEl, clientX, clientY) {
  // 视口坐标 → PDF 点坐标（page-wrap 尺寸 = nat × zoom）
  const pr = pageEl.getBoundingClientRect();
  return {
    x: (clientX - pr.left) / state.zoom / K,
    y: (clientY - pr.top) / state.zoom / K,
  };
}

function wordIndexAtPoint(words, x, y, bodyOnly = false) {
  // 最近词中心（命中词间空隙也能吸附到邻近词）；bodyOnly 时排除页眉页脚
  let best = -1, bestD = Infinity;
  for (const w of words) {
    if (bodyOnly && (w.zone || "body") !== "body") continue;
    const dx = w.x + w.w / 2 - x;
    const dy = w.y + w.h / 2 - y;
    const d = dx * dx + dy * dy;
    if (d < bestD) { bestD = d; best = w.i; }
  }
  return best;
}

function pageElAtRect(rect) {
  const el = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
  return el && el.closest ? el.closest(".page-wrap") : null;
}

function getAnchorFromSelection() {
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || !sel.rangeCount) return null;
  const rects = [...sel.getRangeAt(0).getClientRects()];
  if (!rects.length) return null;

  // 逐矩形收集（跨页天然支持），只取正文词（页眉页脚已被 CSS 排除 + zone 过滤双保险）
  const segs = [];
  for (const rect of rects) {
    const el = pageElAtRect(rect);
    if (!el) continue;
    const words = state.words.get(+el.dataset.page) || [];
    if (!words.length) continue;
    const p = pagePointFromClient(el, rect.left + rect.width / 2, rect.top + rect.height / 2);
    const wi = wordIndexAtPoint(words, p.x, p.y, true);
    if (wi < 0) continue;
    const last = segs[segs.length - 1];
    if (last && last.page === +el.dataset.page && wi - last.we <= 1) {
      last.we = wi;   // 同行/相邻行连续词合并为一段
    } else {
      segs.push({ page: +el.dataset.page, ws: wi, we: wi });
    }
  }
  if (!segs.length) return null;

  const parts = segs.map((s) => {
    const words = state.words.get(s.page) || [];
    return smartJoin(words.slice(s.ws, s.we + 1).map((w) => w.t));
  });
  const first = segs[0];
  return {
    page: first.page,
    word_start: first.ws,
    word_end: segs.length === 1 ? segs[0].we : segs[segs.length - 1].we,
    char_start: 0,
    char_end: 0,
    segments: segs.length > 1 ? segs : null,   // 跨页多段锚点
    text: parts.join(" "),
  };
}

/* ================= 高亮绘制（支持跨页多段） ================= */
function annSegments(ann) {
  if (ann.segments?.length) return ann.segments;
  return [{ page: ann.page, ws: ann.word_start, we: ann.word_end }];
}

function segRows(page, ws, we) {
  // 词区间 → 逐行合并矩形（同一行 = y 接近）
  const words = state.words.get(page) || [];
  const sel = words.slice(ws, we + 1);
  const rows = [];
  for (const w of sel) {
    const last = rows[rows.length - 1];
    if (last && Math.abs(w.y - last.y) < last.h * 0.6) {
      last.x2 = Math.max(last.x2, w.x + w.w);
      last.y = Math.min(last.y, w.y);
      last.h = Math.max(last.h, w.h);
      last.y2 = Math.max(last.y2, w.y + w.h);
    } else {
      rows.push({ x: w.x, y: w.y, x2: w.x + w.w, h: w.h, y2: w.y + w.h });
    }
  }
  return rows;
}

function drawSeg(ann, page, ws, we) {
  if (ws < 0) return;
  const pageEl = document.querySelector(`.page-wrap[data-page="${page}"]`);
  if (!pageEl) return;
  const hl = pageEl.querySelector(".hllayer");
  if (!hl) return;   // 页面内容已被懒加载卸载（占位仍在），重渲染时会重新绘制
  for (const r of segRows(page, ws, we)) {
    const rect = document.createElement("div");
    rect.className = "hl-rect" + (ann.note ? " has-note" : "");
    rect.dataset.annId = ann.id;
    rect.title = "点击查看笔记";
    rect.style.left = `${r.x * K}px`;
    rect.style.top = `${r.y * K}px`;
    rect.style.width = `${Math.max((r.x2 - r.x) * K, 2)}px`;
    rect.style.height = `${(r.y2 - r.y) * K}px`;
    rect.style.background = ann.color || "#FFEB3B";
    rect.style.opacity = String(ann.opacity ?? 0.55);
    rect.addEventListener("click", () => jumpToAnn(ann.id));
    hl.appendChild(rect);
  }
}

function drawAnn(ann) {
  for (const seg of annSegments(ann)) {
    const pageEl = document.querySelector(`.page-wrap[data-page="${seg.page}"]`);
    if (pageEl) pageEl.querySelectorAll(`[data-ann-id="${ann.id}"]`).forEach((e) => e.remove());
    drawSeg(ann, seg.page, seg.ws, seg.we);
  }
}

function drawPageAnns(n) {
  for (const ann of state.anns.values()) {
    if (ann.page === n) drawAnn(ann);
  }
}

/* ================= 批注创建 / 更新 ================= */
function createAnn(anchor, opts = {}) {
  const ann = {
    id: crypto.randomUUID(),
    paper_id: state.paperId,
    supp_id: state.doc.suppId,
    page: anchor.page,
    word_start: anchor.word_start ?? -1,
    word_end: anchor.word_end ?? -1,
    char_start: anchor.char_start ?? 0,
    char_end: anchor.char_end ?? 0,
    segments: anchor.segments || null,   // 跨页多段锚点
    text: anchor.text || "",
    note: opts.note || "",
    color: opts.color || null,
    opacity: opts.opacity ?? state.highlightOpacity,
    kind: opts.kind || (opts.color ? "highlight" : "note"),
  };
  state.anns.set(ann.id, ann);
  queueUpsert(ann);
  drawAnn(ann);
  renderNotesList();
  updateNotesCount();
  return ann;
}

function updateAnn(id, patch, opts = {}) {
  const ann = state.anns.get(id);
  if (!ann) return;
  Object.assign(ann, patch);
  if (ann.note) ann.kind = ann.color ? "both" : "note";
  else if (ann.color) ann.kind = "highlight";
  queueUpsert(ann);
  drawAnn(ann);
  if (opts.refresh) renderNotesList();   // 仅透明度等视觉变更时刷新（note 输入时刷新会打断打字）
  updateNotesCount();
}

function jumpToAnn(id) {
  const ann = state.anns.get(id);
  if (!ann) return;
  gotoPage(ann.page).then(() => {
    const rect = document.querySelector(`.hl-rect[data-ann-id="${id}"]`);
    if (rect) {
      rect.classList.remove("flash");
      void rect.offsetWidth;   // 重启动画
      rect.classList.add("flash");
    }
    openPanel();
    const item = document.querySelector(`.note-item[data-id="${id}"]`);
    item?.scrollIntoView({ behavior: "smooth", block: "center" });
  });
}

async function gotoPage(n) {
  await ensurePage(n);
  const off = pageOffset(n);
  if (off !== null) {
    $("#reader-wrap").scrollTo({ top: off - 20, behavior: "smooth" });
  }
}

/* ================= 笔记侧栏 ================= */
function openPanel() { $("#notes-panel").classList.add("open"); }
function closePanel() { $("#notes-panel").classList.remove("open"); }

function renderNotesList() {
  const list = $("#notes-list");
  const anns = [...state.anns.values()].sort((a, b) => a.page - b.page);
  if (!anns.length) {
    list.innerHTML = `<div class="empty">暂无笔记。选中文字后点「✍ 笔记」或高亮色板。</div>`;
    return;
  }
  list.innerHTML = anns.map((a) => `
    <div class="note-item" data-id="${a.id}">
      <div class="head">
        <span>第 ${a.page} 页</span>
        ${a.color ? `<span class="tag" style="background:${a.color}; opacity:${a.opacity ?? 0.55}">高亮</span>` : `<span class="tag gray">笔记</span>`}
        ${a.color ? `
          <select class="opacity-sel" title="高亮透明度" style="border:1px solid var(--border); border-radius:5px; font-size:11.5px; padding:1px 3px">
            ${[0.3, 0.45, 0.55, 0.7, 0.85].map((v) =>
              `<option value="${v}" ${Math.abs((a.opacity ?? 0.55) - v) < 0.01 ? "selected" : ""}>${Math.round(v * 100)}%</option>`).join("")}
          </select>` : ""}
        <span style="flex:1"></span>
        <button class="btn" data-act="jump">定位</button>
        <button class="btn danger" data-act="del">删除</button>
      </div>
      ${a.text ? `<div class="quote">${escapeHtml(a.text)}</div>` : ""}
      <textarea placeholder="写点笔记…" data-note="${a.id}">${escapeHtml(a.note)}</textarea>
    </div>
  `).join("");

  list.querySelectorAll(".note-item").forEach((item) => {
    const id = item.dataset.id;
    item.querySelector("[data-act=jump]").addEventListener("click", () => jumpToAnn(id));
    item.querySelector("[data-act=del]").addEventListener("click", () => {
      state.anns.delete(id);
      queueDelete(id);
      document.querySelectorAll(`.hl-rect[data-ann-id="${id}"]`).forEach((e) => e.remove());
      renderNotesList();
      updateNotesCount();
    });
    const ta = item.querySelector("textarea");
    ta.addEventListener("input", () => updateAnn(id, { note: ta.value }));
    const os = item.querySelector(".opacity-sel");
    if (os) os.addEventListener("change", () => updateAnn(id, { opacity: +os.value }, { refresh: true }));
  });
}

function updateNotesCount() { $("#notes-count").textContent = state.anns.size; }

/* ================= 选区工具条 ================= */
function showSelbar(rect) {
  const bar = $("#selbar");
  bar.style.display = "flex";
  const x = Math.min(rect.left + rect.width / 2 - bar.offsetWidth / 2, window.innerWidth - bar.offsetWidth - 8);
  bar.style.left = `${Math.max(x, 8)}px`;
  bar.style.top = `${Math.min(rect.bottom + 8, window.innerHeight - 50)}px`;
}
function hideSelbar() { $("#selbar").style.display = "none"; }

/* ================= 多段选区管理 =================
 * 第一次拖选 = 第一段；按住 Shift 再拖动 = 追加新段（可跨页、可多次），
 * 段与段之间不自动填充，只保留每次按下拖动划出的词。 */
function spanElAt(page, wi) {
  return document.querySelector(`.page-wrap[data-page="${page}"] .textlayer span[data-i="${wi}"]`);
}

function bodyRange(words) {
  let first = -1, last = -1;
  for (const w of words) {
    if ((w.zone || "body") !== "body") continue;
    if (first < 0) first = w.i;
    last = w.i;
  }
  return { first, last };
}

function buildDragSegs(start, end) {
  // 起点词到终点词（都已是 body 词）；跨页时中间页整页 body 填充
  if (start.page === end.page) {
    return [{ page: start.page, ws: Math.min(start.wi, end.wi), we: Math.max(start.wi, end.wi) }];
  }
  const [lo, hi] = start.page < end.page ? [start, end] : [end, start];
  const segs = [];
  const r0 = bodyRange(state.words.get(lo.page) || []);
  if (r0.first >= 0) segs.push({ page: lo.page, ws: Math.min(lo.wi, r0.first), we: r0.last });
  for (let p = lo.page + 1; p < hi.page; p++) {
    const r = bodyRange(state.words.get(p) || []);
    if (r.first >= 0) segs.push({ page: p, ws: r.first, we: r.last });
  }
  const r1 = bodyRange(state.words.get(hi.page) || []);
  if (r1.first >= 0) segs.push({ page: hi.page, ws: r1.first, we: Math.max(hi.wi, r1.first) });
  return segs;
}

function pushSegs(segs) {
  for (const seg of segs) {
    const last = state.multiSegs[state.multiSegs.length - 1];
    if (last && last.page === seg.page && seg.ws - last.we <= 1) {
      last.we = Math.max(last.we, seg.we);   // 相邻/重叠段合并
    } else {
      state.multiSegs.push({ ...seg });
    }
  }
}

function anchorFromSegs(segs) {
  if (!segs.length) return null;
  const parts = segs.map((s) => {
    const words = state.words.get(s.page) || [];
    return smartJoin(words.slice(s.ws, s.we + 1).map((w) => w.t));
  });
  return {
    page: segs[0].page,
    word_start: segs[0].ws,
    word_end: segs[segs.length - 1].we,
    char_start: 0, char_end: 0,
    segments: segs.length > 1 ? segs : null,
    text: parts.join(" "),
  };
}

function renderMultiSelection() {
  document.querySelectorAll(".sel-rect").forEach((r) => r.remove());
  const segs = [...state.multiSegs];
  if (state.shiftDragging && state.shiftDragging.lastPage !== null) {
    segs.push(...buildDragSegs(
      { page: state.shiftDragging.page, wi: state.shiftDragging.wi },
      { page: state.shiftDragging.lastPage, wi: state.shiftDragging.lastWi },
    ));
  }
  for (const seg of segs) {
    const hl = document.querySelector(`.page-wrap[data-page="${seg.page}"] .hllayer`);
    if (!hl) continue;
    for (const r of segRows(seg.page, seg.ws, seg.we)) {
      const rect = document.createElement("div");
      rect.className = "sel-rect";
      rect.style.left = `${r.x * K}px`;
      rect.style.top = `${r.y * K}px`;
      rect.style.width = `${Math.max((r.x2 - r.x) * K, 2)}px`;
      rect.style.height = `${(r.y2 - r.y) * K}px`;
      hl.appendChild(rect);
    }
  }
}

function clearMultiSelection() {
  state.multiSegs = [];
  state.shiftDragging = null;
  state.currentAnchor = null;
  window.getSelection().removeAllRanges();
  document.querySelectorAll(".sel-rect").forEach((r) => r.remove());
  hideSelbar();
}

function afterSegsChanged() {
  if (!state.multiSegs.length) return;
  state.currentAnchor = anchorFromSegs(state.multiSegs);
  const lastSeg = state.multiSegs[state.multiSegs.length - 1];
  const span = spanElAt(lastSeg.page, lastSeg.we);
  if (span) showSelbar(span.getBoundingClientRect());
}

document.addEventListener("mousedown", (e) => {
  if (!e.target.closest(".selbar")) hideSelbar();
  const span = e.target.closest?.(".textlayer span");
  if (e.shiftKey && span && (span.dataset.zone || "body") === "body") {
    // Shift+按下：开始追加一段（自定义拖动，段间不填充）
    e.preventDefault();
    const pageEl = span.closest(".page-wrap");
    state.shiftDragging = { page: +pageEl.dataset.page, wi: +span.dataset.i, lastPage: null, lastWi: null };
    if (!state.shiftHintShown) {
      state.shiftHintShown = true;
      toast("Shift+拖动划词可跨页追加多段选择，已选内容会保留");
    }
    return;
  }
  // 点击空白区域（非文字、非面板、非工具条）：清除多段选区
  if (!span && !e.target.closest(".selbar") && !e.target.closest("#ref-tip")
    && !e.target.closest(".notes-panel") && !e.target.closest(".chat-panel") && !e.target.closest(".mm-overlay")) {
    clearMultiSelection();
  }
});

document.addEventListener("mousemove", (e) => {
  if (!state.shiftDragging) return;
  const span = document.elementFromPoint(e.clientX, e.clientY)?.closest?.(".textlayer span");
  if (span && (span.dataset.zone || "body") === "body") {
    const pageEl = span.closest(".page-wrap");
    state.shiftDragging.lastPage = +pageEl.dataset.page;
    state.shiftDragging.lastWi = +span.dataset.i;
    renderMultiSelection();
  }
});

document.addEventListener("mouseup", (e) => {
  if (e.target.closest(".selbar")) return;
  if (state.shiftDragging) {
    const d = state.shiftDragging;
    state.shiftDragging = null;
    if (d.lastPage !== null) {
      pushSegs(buildDragSegs({ page: d.page, wi: d.wi }, { page: d.lastPage, wi: d.lastWi }));
      renderMultiSelection();
      afterSegsChanged();
    }
    return;
  }
  // 普通拖选：转为多段选区管理（视觉从浏览器蓝换为自定义层，样式一致）
  setTimeout(() => {
    const anchor = getAnchorFromSelection();
    if (!anchor) return;
    state.multiSegs = [];
    pushSegs(anchor.segments || [{ page: anchor.page, ws: anchor.word_start, we: anchor.word_end }]);
    window.getSelection().removeAllRanges();
    renderMultiSelection();
    afterSegsChanged();
  }, 10);
});
document.addEventListener("scroll", () => hideSelbar(), true);

$("#selbar").addEventListener("mousedown", (e) => e.preventDefault());   // 保住选区

// 新创建高亮的默认透明度
$("#sel-opacity").addEventListener("change", (e) => {
  state.highlightOpacity = +e.target.value;
  toast(`新高的默认透明度已设为 ${Math.round(state.highlightOpacity * 100)}%`);
});

document.querySelectorAll("#selbar .color-dot").forEach((dot) => {
  dot.addEventListener("click", () => {
    if (!state.currentAnchor) return;
    createAnn(state.currentAnchor, { color: dot.dataset.color });
    window.getSelection().removeAllRanges();
    hideSelbar();
    toast("已高亮（自动保存中）");
  });
});

$("#sel-note").addEventListener("click", () => {
  if (!state.currentAnchor) return;
  const ann = createAnn(state.currentAnchor, {});
  window.getSelection().removeAllRanges();
  hideSelbar();
  openPanel();
  setTimeout(() => {
    const ta = document.querySelector(`.note-item[data-id="${ann.id}"] textarea`);
    ta?.focus();
  }, 260);
});

$("#sel-translate").addEventListener("click", async () => {
  if (!state.currentAnchor) return;
  const anchor = state.currentAnchor;
  window.getSelection().removeAllRanges();
  hideSelbar();
  state.translateAnchor = anchor;
  $("#tr-src").textContent = anchor.text;
  $("#tr-result").textContent = "翻译中…";
  $("#tr-cached").textContent = "";
  $("#translate-modal").style.display = "flex";
  try {
    const data = await API.post("/api/v1/translate", { text: anchor.text });
    $("#tr-result").textContent = data.translated;
    $("#tr-cached").textContent = data.cached ? "（缓存）" : "";
    state.translated = data.translated;
  } catch (e) {
    $("#tr-result").innerHTML = `<span style="color:var(--danger)">${escapeHtml(e.message)}</span>`;
    state.translated = null;
  }
});

$("#sel-copy").addEventListener("click", () => {
  if (!state.currentAnchor) return;
  navigator.clipboard.writeText(state.currentAnchor.text).then(() => toast("已复制"));
  window.getSelection().removeAllRanges();
  hideSelbar();
});

/* ================= 缩放 ================= */
function dpiForZoom(z) {
  return z > 3 ? 600 : z > 1.5 ? 300 : 150;
}

function updatePageImages() {
  // 缩放跨越清晰度档位时，为已渲染页面请求更高 dpi 的渲染图（CSS 尺寸不变，仅像素密度提升）
  const dpi = dpiForZoom(state.zoom);
  if (dpi === state.currentDpi) return;
  state.currentDpi = dpi;
  document.querySelectorAll(".page-wrap img.page-img").forEach((img) => {
    const n = +img.closest(".page-wrap").dataset.page;
    img.src = `/api/v1/papers/${state.paperId}/pages/${n}/image?doc=${docParam()}&dpi=${dpi}`;
  });
}

function applyZoom() {
  document.querySelectorAll(".page-wrap").forEach((el) => {
    const n = +el.dataset.page;
    const nat = state.pageNat.get(n);
    if (!nat) return;
    el.style.width = `${nat.w * state.zoom}px`;
    el.style.height = `${nat.h * state.zoom}px`;
    const inner = el.querySelector(".page-inner");
    if (inner) inner.style.transform = `scale(${state.zoom})`;
    state.pageH.set(n, nat.h * state.zoom);
  });
  state.offsetTop.clear();
  updatePageImages();
  lazyRender();
}

function fitWidth() {
  const nat = state.pageNat.get(1) || state.pageNat.get(state.currentPage);
  if (!nat) return;
  const wrap = $("#reader-wrap");
  state.zoom = Math.max((wrap.clientWidth - 80) / nat.w, 0.2);
  applyZoom();
}

$("#btn-zoom-in").addEventListener("click", () => { state.zoom = Math.min(state.zoom * 1.25, 4); applyZoom(); });
$("#btn-zoom-out").addEventListener("click", () => { state.zoom = Math.max(state.zoom / 1.25, 0.3); applyZoom(); });
$("#btn-zoom-fit").addEventListener("click", fitWidth);

/* ---------- Ctrl+滚轮缩放（以鼠标位置为锚点，缩放后该内容点保持不动） ---------- */
$("#reader-wrap").addEventListener("wheel", (e) => {
  if (!e.ctrlKey) return;
  e.preventDefault();   // 阻止浏览器默认的页面缩放
  const old = state.zoom;
  state.zoom = Math.min(Math.max(state.zoom * (e.deltaY < 0 ? 1.1 : 0.9), 0.3), 4);
  const wrap = $("#reader-wrap");
  const rect = wrap.getBoundingClientRect();
  const contentX = e.clientX - rect.left + wrap.scrollLeft;
  const contentY = e.clientY - rect.top + wrap.scrollTop;
  applyZoom();
  const ratio = state.zoom / old;
  wrap.scrollLeft = contentX * ratio - (e.clientX - rect.left);
  wrap.scrollTop = contentY * ratio - (e.clientY - rect.top);
}, { passive: false });

/* ---------- 拖拽平移页面：中键拖动，或左键拖动页面四周空白区 ---------- */
let panning = null;
const readerWrap = $("#reader-wrap");
readerWrap.addEventListener("mousedown", (e) => {
  if (e.button !== 1 && e.target.closest(".page-wrap")) return;   // 左键在页面上=选文字，不启动平移
  panning = { x: e.clientX, y: e.clientY, sl: readerWrap.scrollLeft, st: readerWrap.scrollTop };
  e.preventDefault();   // 抑制中键默认的 autoscroll
});
document.addEventListener("mousemove", (e) => {
  if (!panning) return;
  readerWrap.scrollLeft = panning.sl - (e.clientX - panning.x);
  readerWrap.scrollTop = panning.st - (e.clientY - panning.y);
});
document.addEventListener("mouseup", () => { panning = null; });

/* ================= 导航与事件 ================= */
$("#btn-notes").addEventListener("click", () => {
  const panel = $("#notes-panel");
  panel.classList.contains("open") ? closePanel() : openPanel();
});

// 面板头部 ✕ 按钮 / Esc / 点击阅读区任意处均可收起
$("#btn-notes-close").addEventListener("click", closePanel);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { closePanel(); clearMultiSelection(); }
});
$("#reader-wrap").addEventListener("mousedown", (e) => {
  if (!e.target.closest(".notes-panel") && !e.target.closest("#btn-notes")) closePanel();
});

$("#btn-page-note").addEventListener("click", () => {
  const ann = createAnn({ page: state.currentPage, word_start: -1, word_end: -1, text: "" }, { kind: "note" });
  openPanel();
  setTimeout(() => document.querySelector(`.note-item[data-id="${ann.id}"] textarea`)?.focus(), 260);
});

// 扫描版页面的"添加页级笔记"
$("#pages").addEventListener("click", (e) => {
  const btn = e.target.closest("[data-page-note]");
  if (!btn) return;
  createAnn({ page: +btn.dataset.pageNote, word_start: -1, word_end: -1, text: "" }, { kind: "note" });
  openPanel();
  toast("已添加页级笔记");
});

/* ---------- 翻译面板 ---------- */
$("#btn-tr-close").addEventListener("click", () => { $("#translate-modal").style.display = "none"; });
$("#btn-tr-copy").addEventListener("click", () => {
  if (state.translated) navigator.clipboard.writeText(state.translated).then(() => toast("已复制译文"));
});
$("#btn-tr-note").addEventListener("click", () => {
  if (!state.translated) { toast("暂无译文"); return; }
  const anchor = state.translateAnchor;
  if (!anchor) return;
  const ann = createAnn(anchor, { note: `【译文】${state.translated}` });
  $("#translate-modal").style.display = "none";
  openPanel();
  setTimeout(() => document.querySelector(`.note-item[data-id="${ann.id}"] textarea`)?.focus(), 260);
});

$("#btn-back").addEventListener("click", async () => {
  $("#btn-back").disabled = true;
  await flush();     // 退出阅读：显式 flush 成功后才离开
  location.href = "index.html";
});

$("#reader-wrap").addEventListener("scroll", lazyRender, { passive: true });

/* ================= 初始化 ================= */
(async function init() {
  try {
    state.paper = await API.get(`/api/v1/papers/${state.paperId}`);
  } catch (e) {
    toast(e.message);
    location.href = "index.html";
    return;
  }
  document.title = `${state.paper.title} - 文献管家`;
  $("#paper-title").textContent = state.paper.title;
  state.pageCount = state.paper.pdf_pages || 1;
  $("#page-ind").textContent = `第 1 / ${state.pageCount} 页`;

  // 设置页配置的默认高亮透明度（映射到最近档位；划词工具条仍可临时改）
  try {
    const settings = await API.get("/api/v1/settings");
    const v = +settings.highlight_opacity || 0.55;
    const levels = [0.3, 0.45, 0.55, 0.7, 0.85];
    state.highlightOpacity = levels.reduce((a, b) => (Math.abs(b - v) < Math.abs(a - v) ? b : a));
    $("#sel-opacity").value = String(state.highlightOpacity);
  } catch (e) { /* 设置读取失败时用默认值 */ }

  // 补充材料列表 → 文档切换栏
  const suppRes = await API.get(`/api/v1/papers/${state.paperId}/supplements`);
  state.supplements = suppRes.items;
  renderDocBar();

  const res = await API.get(`/api/v1/papers/${state.paperId}/annotations?supp_id=0`);
  for (const a of res.items) state.anns.set(a.id, a);
  updateNotesCount();
  renderNotesList();

  // 先建全部占位（滚动条/跳页位置正确），再渲染第一页与可视区
  const meta = await API.get(`/api/v1/papers/${state.paperId}/pages/meta?doc=${docParam()}`);
  createPlaceholders(meta.pages);
  await ensurePage(1);
  fitWidth();

  // URL 带 page 参数时（如手绘匹配跳转）直接定位到该页
  const startPage = +new URLSearchParams(location.search).get("page") || 1;
  if (startPage > 1 && startPage <= state.pageCount) gotoPage(startPage);
})();
