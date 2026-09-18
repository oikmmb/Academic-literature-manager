/** 导入流程：上传 PDF → 展示提取元数据 → 可选 DOI 联网补全 / 补充材料 → 确认入库。 */
const $ = (sel) => document.querySelector(sel);
let draftId = null;
const suppFiles = [];   // 已添加到 draft 的补充材料 {label, pdf_pages}

(async function showSaveDir() {
  try {
    const s = await API.get("/api/v1/settings");
    $("#import-pdf-dir").textContent = s.pdf_dir
      ? `保存到：${s.pdf_dir}（可在「⚙ 设置」修改）`
      : "保存到默认目录（可在「⚙ 设置」自定义保存位置）";
  } catch (e) { /* 忽略 */ }
})();

/* ---------- 上传 ---------- */
const dz = $("#dropzone");
dz.addEventListener("click", () => $("#file-input").click());
dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("drag"); });
dz.addEventListener("dragleave", () => dz.classList.remove("drag"));
dz.addEventListener("drop", (e) => {
  e.preventDefault();
  dz.classList.remove("drag");
  if (e.dataTransfer.files.length) uploadFile(e.dataTransfer.files[0]);
});
$("#file-input").addEventListener("change", (e) => {
  if (e.target.files.length) uploadFile(e.target.files[0]);
  e.target.value = "";
});

async function uploadFile(file) {
  if (!file.name.toLowerCase().endsWith(".pdf")) { toast("仅支持 PDF 文件"); return; }
  dz.querySelector(".big").textContent = "⏳";
  dz.style.pointerEvents = "none";
  try {
    const fd = new FormData();
    fd.append("file", file);
    const data = await API.upload("/api/v1/import", fd);
    draftId = data.draft_id;
    fillForm(data.metadata);
    $("#step-upload").style.display = "none";
    $("#step-form").style.display = "block";
    toast("已提取元数据，请确认");
  } catch (e) {
    toast(e.message);
  } finally {
    dz.querySelector(".big").textContent = "📄";
    dz.style.pointerEvents = "";
  }
}

/* ---------- 补充材料 ---------- */
function renderSuppList() {
  const box = $("#supp-list");
  if (!suppFiles.length) { box.innerHTML = ""; return; }
  box.innerHTML = suppFiles.map((s) => `
    <span class="tag" style="margin-bottom:4px">📎 ${escapeHtml(s.label)}（${s.pdf_pages}页）
      <button data-del="${s.sid}" style="border:none;background:none;cursor:pointer;color:var(--danger)">✕</button>
    </span>
  `).join("");
  box.querySelectorAll("[data-del]").forEach((b) => {
    b.addEventListener("click", async () => {
      // 同步删除服务端 draft 中的文件，避免 confirm 时误导入
      try {
        const data = await API.delete(`/api/v1/import/${draftId}/supplements/${b.dataset.del}`);
        suppFiles.length = 0;
        suppFiles.push(...data.supplements);
        renderSuppList();
        toast("已移除");
      } catch (err) { toast(err.message); }
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
      const data = await API.upload(`/api/v1/import/${draftId}/supplements`, fd);
      suppFiles.length = 0;
      suppFiles.push(...data.supplements);
      renderSuppList();
      toast(`已添加补充材料：${f.name}`);
    } catch (err) { toast(err.message); }
  }
});

/* ---------- 表单 ---------- */
function fillForm(m) {
  $("#f-title").value = m.title ?? "";
  $("#f-first").value = m.first_author ?? "";
  $("#f-corr").value = m.corresponding_author ?? "";
  $("#f-authors").value = (m.authors || []).join(", ");
  $("#f-subject").value = "";
  $("#f-year").value = m.year ?? "";
  $("#f-journal").value = m.journal ?? "";
  $("#f-volume").value = m.volume ?? "";
  $("#f-issue").value = m.issue ?? "";
  $("#f-doi").value = m.doi ?? "";
  $("#f-abstract").value = m.abstract ?? "";
}

$("#btn-back").addEventListener("click", () => {
  $("#step-form").style.display = "none";
  $("#step-upload").style.display = "block";
  draftId = null;
});

$("#btn-doi-lookup").addEventListener("click", async () => {
  const doi = $("#f-doi").value.trim();
  if (!doi) { toast("请先填写 DOI"); return; }
  const btn = $("#btn-doi-lookup");
  btn.disabled = true; btn.textContent = "查询中…";
  try {
    const m = await API.get(`/api/v1/crossref/lookup?doi=${encodeURIComponent(doi)}`);
    if (!m.title) { toast("未查到该 DOI"); return; }
    // 用 Crossref 数据覆盖（用户已填的作者/主题保留）
    const authors = $("#f-authors").value;
    $("#f-title").value = m.title ?? $("#f-title").value;
    if (authors) $("#f-authors").value = m.authors?.length ? m.authors.join(", ") : authors;
    $("#f-first").value = m.first_author ?? $("#f-first").value;
    $("#f-year").value = m.year ?? $("#f-year").value;
    $("#f-journal").value = m.journal ?? $("#f-journal").value;
    $("#f-volume").value = m.volume ?? "";
    $("#f-issue").value = m.issue ?? "";
    $("#f-abstract").value = m.abstract ?? $("#f-abstract").value;
    toast("已从 Crossref 补全");
  } catch (e) {
    toast(e.message);
  } finally {
    btn.disabled = false; btn.textContent = "联网补全";
  }
});

$("#btn-confirm").addEventListener("click", async () => {
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
  const btn = $("#btn-confirm");
  btn.disabled = true; btn.textContent = "保存中…";
  try {
    await API.post(`/api/v1/import/${draftId}/confirm`, body);
    toast("已入库");
    location.href = "index.html";
  } catch (e) {
    toast(e.message);
    btn.disabled = false; btn.textContent = "保存入库";
  }
});
