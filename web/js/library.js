/** 文献库：列表、搜索、排序、增删改弹窗（M2 加分类视图与导入）。 */
const state = {
  view: "all",
  editingId: null,
};

const $ = (sel) => document.querySelector(sel);

async function loadList() {
  const q = $("#search").value.trim();
  const [sort_by, order] = $("#sort").value.split(":");
  const params = new URLSearchParams({ sort_by, order, limit: "200" });
  if (q) params.set("q", q);
  // 分类视图的筛选条件
  if (state.view === "year" && state.groupKey) params.set("year_from", state.groupKey);
  if (state.view === "subject" && state.groupKey) params.set("subject", state.groupKey);
  if (state.view === "first_author" && state.groupKey) params.set("first_author", state.groupKey);
  if (state.view === "corresponding_author" && state.groupKey) params.set("corresponding_author", state.groupKey);

  const data = await API.get(`/api/v1/papers?${params}`);
  renderList(data.items);
}

function renderList(items) {
  const list = $("#list");
  // 分组详情模式：顶部返回条
  const oldBar = $("#group-backbar");
  if (state.groupKey) {
    if (!oldBar) list.parentNode.insertBefore(renderBackbar(), list);
    if (oldBar) oldBar.style.display = "";
  } else if (oldBar) {
    oldBar.remove();
  }
  if (!items.length) {
    list.innerHTML = `<div class="empty">暂无文献，点击右上角「导入文献」开始</div>`;
    return;
  }
  list.innerHTML = items.map((p) => `
    <div class="card" data-id="${p.id}">
      <div class="info">
        <div class="title">${escapeHtml(p.title)}</div>
        <div class="meta">
          ${p.first_author ? `👤 一作：${escapeHtml(p.first_author)}　` : ""}
          ${p.corresponding_author ? `✉ 通讯：${escapeHtml(p.corresponding_author)}　` : ""}
          <br>
          ${p.journal ? `${escapeHtml(p.journal)}　` : ""}
          ${p.year ?? ""}
          <span class="tag">${escapeHtml(p.subject || "未分类")}</span>
          <span class="tag gray">${p.has_pdf ? `📄 ${p.pdf_pages}页` : "无PDF"}</span>
          ${p.doi ? `<span class="tag gray">${escapeHtml(p.doi)}</span>` : ""}
        </div>
      </div>
      <button class="btn danger card-del" data-del="${p.id}" title="删除文献">🗑</button>
    </div>
  `).join("");

  list.querySelectorAll(".card").forEach((card) => {
    card.addEventListener("click", (e) => {
      if (e.target.closest(".card-del")) return;
      openPaper(+card.dataset.id);
    });
  });
  list.querySelectorAll(".card-del").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("确定删除该文献？其 PDF、补充材料和全部批注将被一并删除。")) return;
      try {
        await API.delete(`/api/v1/papers/${btn.dataset.del}`);
        toast("文献已删除");
        loadList();
      } catch (e) { toast(e.message); }
    });
  });
}

function openPaper(id) {
  // 有 PDF 进阅读器，否则弹编辑框
  API.get(`/api/v1/papers/${id}`).then((p) => {
    if (p.has_pdf) location.href = `reader-host.html?id=${id}`;
    else openEditor(p);
  });
}

/* ---------- 分类分组视图 ---------- */
const GROUP_TITLES = {
  year: "按发表时间", subject: "按文献主题",
  first_author: "按第一作者", corresponding_author: "按通讯作者",
};

async function renderGroups() {
  const data = await API.get(`/api/v1/papers/groups/${state.view}`);
  const list = $("#list");
  const total = data.groups.reduce((s, g) => s + g.count, 0);
  list.innerHTML = `
    <div style="margin-bottom:12px; color:var(--text-2)">
      ${GROUP_TITLES[state.view]} · 共 ${data.groups.length} 组 / ${total} 篇
    </div>
    ${data.groups.map((g) => `
      <div class="card group-card" data-key="${encodeURIComponent(g.key)}">
        <div class="info">
          <div class="title">${escapeHtml(g.label)}</div>
        </div>
        <div class="tag gray">${g.count} 篇</div>
      </div>
    `).join("")}
  `;
  list.querySelectorAll(".group-card").forEach((card) => {
    card.addEventListener("click", () => {
      state.groupKey = decodeURIComponent(card.dataset.key);
      loadList();
    });
  });
}

function renderBackbar() {
  const bar = document.createElement("div");
  bar.id = "group-backbar";
  bar.style.cssText = "padding:8px 0;";
  bar.innerHTML = `
    <button class="btn" id="btn-group-back">← ${GROUP_TITLES[state.view]}</button>
    <span style="color:var(--text-2); margin-left:10px">当前组：${escapeHtml(state.groupKey)}</span>
  `;
  bar.querySelector("#btn-group-back").addEventListener("click", () => {
    state.groupKey = null;
    renderGroups();
  });
  return bar;
}

/* ---------- 编辑弹窗 ---------- */
const editSupps = [];   // 编辑弹窗中当前文献的补充材料列表

async function openEditor(p) {
  state.editingId = p.id;
  $("#paper-modal-title").textContent = p.id ? "编辑文献" : "新建文献";
  $("#f-title").value = p.title ?? "";
  $("#f-first").value = p.first_author ?? "";
  $("#f-corr").value = p.corresponding_author ?? "";
  $("#f-authors").value = (p.authors || []).join(", ");
  $("#f-subject").value = p.subject ?? "";
  $("#f-year").value = p.year ?? "";
  $("#f-journal").value = p.journal ?? "";
  $("#f-volume").value = p.volume ?? "";
  $("#f-issue").value = p.issue ?? "";
  $("#f-doi").value = p.doi ?? "";
  $("#f-abstract").value = p.abstract ?? "";
  $("#paper-modal").style.display = "flex";

  // 补充材料管理：仅编辑已有文献时显示
  const isEdit = !!p.id;
  $("#supp-area").style.display = isEdit ? "" : "none";
  $("#btn-delete").style.display = isEdit ? "" : "none";
  editSupps.length = 0;
  if (isEdit) {
    try {
      const res = await API.get(`/api/v1/papers/${p.id}/supplements`);
      editSupps.push(...res.items);
    } catch (e) { /* 忽略加载失败 */ }
  }
  renderEditSupps();
}

function renderEditSupps() {
  const box = $("#supp-list");
  if (!box) return;
  if (!editSupps.length) {
    box.innerHTML = `<div style="font-size:12.5px;color:var(--text-2)">暂无补充材料</div>`;
    return;
  }
  box.innerHTML = editSupps.map((s) => `
    <span class="tag" style="margin-bottom:4px">📎 ${escapeHtml(s.label)}（${s.pdf_pages}页）
      <button data-rm="${s.id}" style="border:none;background:none;cursor:pointer;color:var(--danger)">✕</button>
    </span>
  `).join("");
  box.querySelectorAll("[data-rm]").forEach((b) => {
    b.addEventListener("click", async () => {
      if (!confirm(`确定删除补充材料「${editSupps.find((s) => s.id === +b.dataset.rm)?.label}」？`)) return;
      try {
        await API.delete(`/api/v1/supplements/${b.dataset.rm}`);
        const idx = editSupps.findIndex((s) => s.id === +b.dataset.rm);
        if (idx >= 0) editSupps.splice(idx, 1);
        renderEditSupps();
        toast("已删除");
      } catch (e) { toast(e.message); }
    });
  });
}

$("#btn-add-supp").addEventListener("click", () => $("#supp-input").click());
$("#supp-input").addEventListener("change", async (e) => {
  const files = [...e.target.files];
  e.target.value = "";
  for (const f of files) {
    if (!f.name.toLowerCase().endsWith(".pdf")) { toast("仅支持 PDF 文件"); continue; }
    try {
      const fd = new FormData();
      fd.append("file", f);
      const data = await API.upload(`/api/v1/papers/${state.editingId}/supplements`, fd);
      editSupps.push(data);
      renderEditSupps();
      toast(`已添加：${data.label}`);
    } catch (err) { toast(err.message); }
  }
});

$("#btn-delete").addEventListener("click", async () => {
  if (!confirm("确定删除该文献？其 PDF、补充材料和全部批注将被一并删除。")) return;
  try {
    await API.delete(`/api/v1/papers/${state.editingId}`);
    closeEditor();
    loadList();
    toast("文献已删除");
  } catch (e) { toast(e.message); }
});

async function saveEditor() {
  const title = $("#f-title").value.trim();
  if (!title) { toast("标题不能为空"); return; }
  const body = {
    title,
    first_author: $("#f-first").value.trim() || null,
    corresponding_author: $("#f-corr").value.trim() || null,
    authors: $("#f-authors").value.split(/[,，]/).map((s) => s.trim()).filter(Boolean),
    subject: $("#f-subject").value.trim() || null,
    year: $("#f-year").value ? +$("#f-year").value : null,
    journal: $("#f-journal").value.trim() || null,
    volume: $("#f-volume").value.trim() || null,
    issue: $("#f-issue").value.trim() || null,
    doi: $("#f-doi").value.trim() || null,
    abstract: $("#f-abstract").value.trim() || null,
  };
  try {
    if (state.editingId) await API.put(`/api/v1/papers/${state.editingId}`, body);
    else await API.post("/api/v1/papers", body);
    closeEditor();
    loadList();
    toast("已保存");
  } catch (e) { toast(e.message); }
}

function closeEditor() {
  $("#paper-modal").style.display = "none";
  state.editingId = null;
}

/* ---------- 导航 ---------- */
document.querySelectorAll(".nav-item[data-view]").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    state.view = btn.dataset.view;
    state.groupKey = null;
    if (state.view !== "all") renderGroups();
    else loadList();
  });
});

$("#search").addEventListener("input", () => { clearTimeout(state._t); state._t = setTimeout(loadList, 250); });
$("#sort").addEventListener("change", loadList);
$("#btn-cancel").addEventListener("click", closeEditor);
$("#btn-save").addEventListener("click", saveEditor);
$("#btn-import").addEventListener("click", () => { location.href = "import.html"; });
$("#btn-match").addEventListener("click", () => { location.href = "match.html"; });
$("#nav-settings").addEventListener("click", () => { location.href = "settings.html"; });

loadList();
