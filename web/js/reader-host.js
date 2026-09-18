/** 阅读宿主页：多文献 tab 切换 + 双文献并排对比。
 *  每个 tab = 一个 reader.html 的 iframe（**实例持久化**，切换只移动 DOM 节点不重载，
 *  滚动位置/缩放/批注等状态天然隔离且全程保留）。 */
const $ = (sel) => document.querySelector(sel);

const host = {
  tabs: [],        // [{id, title, page?, iframe?}]
  active: null,    // 当前激活的文献 id
  splitIds: null,  // 并排模式 [idA, idB]，null = 单篇
};

/* ---------- tab 管理 ---------- */
function renderTabs() {
  const bar = $("#tabbar");
  bar.querySelectorAll(".host-tab").forEach((t) => t.remove());
  host.tabs.forEach((t) => {
    const el = document.createElement("div");
    el.className = "host-tab" + (t.id === host.active ? " active" : "");
    el.dataset.id = t.id;
    el.innerHTML = `
      <span class="t-label" title="${escapeHtml(t.title)}">${escapeHtml(t.title)}</span>
      ${host.splitIds && host.splitIds.includes(t.id) ? `<span class="t-split">⇋</span>` : ""}
      <span class="t-close" data-close="${t.id}">✕</span>`;
    el.addEventListener("click", (e) => {
      if (e.target.closest("[data-close]")) return;
      host.active = t.id;
      if (host.splitIds && !host.splitIds.includes(t.id)) host.splitIds = null;   // 点非并排 tab → 退出并排
      renderAll();
    });
    el.querySelector("[data-close]").addEventListener("click", () => closeTab(t.id));
    bar.appendChild(el);
  });
  const hint = $("#split-hint");
  hint.textContent = host.splitIds
    ? "并排对比中：拖动中间分隔条调整宽度"
    : "提示：点「⇋ 并排对比」将当前文献与相邻标签并排";
}

async function openTab(id, page) {
  const exist = host.tabs.find((t) => t.id === id);
  if (exist) {
    if (page && !exist.page) { exist.page = page; exist.iframe.src = `reader.html?id=${id}&page=${page}`; }
    host.active = id;
    if (host.splitIds && !host.splitIds.includes(id)) host.splitIds = null;
    renderAll();
    return;
  }
  try {
    const p = await API.get(`/api/v1/papers/${id}`);
    host.tabs.push({ id, title: p.title, page: page || null });
  } catch (e) {
    toast(e.message);
    return;
  }
  host.active = id;
  host.splitIds = null;
  renderAll();
}

function closeTab(id) {
  const idx = host.tabs.findIndex((t) => t.id === id);
  if (idx < 0) return;
  host.tabs.splice(idx, 1);
  if (host.splitIds?.includes(id)) host.splitIds = null;
  if (host.active === id) host.active = host.tabs[Math.min(idx, host.tabs.length - 1)]?.id ?? null;
  if (!host.tabs.length) { location.href = "index.html"; return; }
  renderAll();
}

/* ---------- 渲染面板（iframe 实例持久化，仅移动 DOM 节点） ---------- */
function renderAll() {
  renderTabs();
  const panes = $("#panes");
  panes.innerHTML = "";
  const visible = (host.splitIds || [host.active]).filter(Boolean);

  visible.forEach((id, i) => {
    if (i > 0) {
      const bar = document.createElement("div");
      bar.className = "host-splitbar";
      panes.appendChild(bar);
    }
    const t = host.tabs.find((x) => x.id === id);
    if (!t) return;
    if (!t.iframe) {
      t.iframe = document.createElement("iframe");
      t.iframe.src = t.page ? `reader.html?id=${id}&page=${t.page}` : `reader.html?id=${id}`;
      t.iframe.title = t.title;
    }
    const pane = document.createElement("div");
    pane.className = "host-pane";
    pane.appendChild(t.iframe);   // 移动节点：切换不重载，状态保留
    panes.appendChild(pane);
  });
  enableSplitDrag();
}

/* 分隔条拖动（并排时调宽度） */
function enableSplitDrag() {
  document.querySelectorAll(".host-splitbar").forEach((bar) => {
    bar.addEventListener("mousedown", (e) => {
      e.preventDefault();
      const panes = $("#panes");
      const left = bar.previousElementSibling, right = bar.nextElementSibling;
      const move = (ev) => {
        const total = panes.clientWidth;
        const x = ev.clientX - panes.getBoundingClientRect().left;
        const ratio = Math.min(Math.max(x / total, 0.2), 0.8);
        left.style.flex = `${ratio}`;
        right.style.flex = `${1 - ratio}`;
      };
      document.addEventListener("mousemove", move);
      document.addEventListener("mouseup", () => {
        document.removeEventListener("mousemove", move);
      }, { once: true });
    });
  });
}

/* ---------- 并排 ---------- */
$("#btn-split").addEventListener("click", () => {
  if (host.tabs.length < 2) { toast("需要至少打开两篇文献才能并排对比"); return; }
  if (host.splitIds) { host.splitIds = null; renderAll(); return; }
  const idx = host.tabs.findIndex((t) => t.id === host.active);
  const other = idx > 0 ? host.tabs[idx - 1] : host.tabs[idx + 1];
  host.splitIds = [host.active, other.id];
  renderAll();
  toast("已并排对比，拖动中间分隔条可调整宽度");
});

/* ---------- 添加文献弹窗 ---------- */
async function openPicker() {
  const list = $("#picker-list");
  $("#picker").style.display = "flex";
  list.innerHTML = `<div style="text-align:center; color:var(--text-2); padding:20px">加载中…</div>`;
  const data = await API.get("/api/v1/papers?limit=200&sort_by=created_at&order=desc");
  list.innerHTML = data.items.map((p) => `
    <div class="match-card" data-pick="${p.id}" style="cursor:pointer">
      <div class="info">
        <div style="font-weight:600">${escapeHtml(p.title)}</div>
        <div class="match-on">${p.first_author ? escapeHtml(p.first_author) + " · " : ""}${p.year ?? ""}${p.has_pdf ? " · 📄" : ""}</div>
      </div>
    </div>
  `).join("") || `<div class="empty">文献库为空</div>`;
  list.querySelectorAll("[data-pick]").forEach((el) => {
    el.addEventListener("click", () => {
      $("#picker").style.display = "none";
      openTab(+el.dataset.pick);
    });
  });
}
$("#btn-add-paper").addEventListener("click", openPicker);
$("#picker-close").addEventListener("click", () => { $("#picker").style.display = "none"; });
$("#picker").addEventListener("click", (e) => {
  if (e.target === e.currentTarget) $("#picker").style.display = "none";
});

/* ---------- 初始化 ---------- */
(function init() {
  const params = new URLSearchParams(location.search);
  const firstId = +params.get("id");
  if (!firstId) { location.href = "index.html"; return; }
  openTab(firstId, params.get("page"));
})();
