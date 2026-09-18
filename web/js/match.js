/** 图片匹配：粘贴/拖入图片 → OCR 匹配本地库 → 未命中 Crossref 联网补录。
 */
const $ = (sel) => document.querySelector(sel);
let lastResult = null;

/* ---------- 匹配流程 ---------- */

async function runMatch(dataUrl) {
  $("#step-input").style.display = "none";
  $("#step-result").style.display = "block";
  $("#preview-img").src = dataUrl;
  $("#result-title").innerHTML = `<span class="spinner"></span>OCR 识别中（首次运行需加载模型，请稍候）…`;
  $("#result-sub").textContent = "";
  $("#matches-panel").innerHTML = "";
  $("#crossref-panel").style.display = "none";
  try {
    const data = await API.post("/api/v1/ocr/match", { image_base64: dataUrl });
    lastResult = data;
    renderResult(data);
  } catch (e) {
    $("#result-title").innerHTML = `<span style="color:var(--danger)">匹配失败：${escapeHtml(e.message)}</span>`;
  }
}

function renderResult(data) {
  const top3 = data.top3 || [];
  $("#ocr-preview").textContent = data.raw_text || "";
  $("#ocr-preview").style.display = "block";

  if (top3.length && top3[0].score >= 55) {
    $("#result-title").textContent = `找到 ${top3.length} 个匹配`;
    $("#result-sub").textContent = `最高相似度 ${top3[0].score}%`;
    $("#matches-panel").innerHTML = top3.map((m) => `
      <div class="match-card">
        <div class="info">
          <div style="font-weight:600">${escapeHtml(m.title)}</div>
          <div class="match-on">匹配字段：${matchOnLabel(m.match_on)}${m.year ? ` · ${m.year}` : ""}</div>
        </div>
        <span class="score">${m.score}%</span>
        <button class="btn primary" data-open="${m.paper_id}">打开</button>
      </div>
    `).join("");
    $("#matches-panel").querySelectorAll("[data-open]").forEach((btn) => {
      btn.addEventListener("click", () => { location.href = `reader-host.html?id=${btn.dataset.open}`; });
    });
  } else {
    $("#result-title").textContent = top3.length ? "匹配度较低" : "本地库未找到匹配";
    $("#result-sub").textContent = "可尝试联网从 Crossref 补录为新的文献条目";
    $("#matches-panel").innerHTML = top3.map((m) => `
      <div class="match-card">
        <div class="info">
          <div>${escapeHtml(m.title)}</div>
          <div class="match-on">匹配字段：${matchOnLabel(m.match_on)}</div>
        </div>
        <span class="score" style="color:var(--text-2); background:#f1f3f6">${m.score}%</span>
        <button class="btn" data-open="${m.paper_id}">打开</button>
      </div>
    `).join("") || `<div class="loading">本地库无相似文献</div>`;
    $("#matches-panel").querySelectorAll("[data-open]").forEach((btn) => {
      btn.addEventListener("click", () => { location.href = `reader-host.html?id=${btn.dataset.open}`; });
    });
    // 补录面板
    $("#crossref-panel").style.display = "block";
    $("#cr-query").value = (data.raw_text || "").split("\n").slice(0, 4).join(" ");
    $("#btn-cr-doi").style.display = data.doi ? "" : "none";
  }
}

function matchOnLabel(k) {
  return { title: "标题", first_author: "第一作者", journal: "期刊" }[k] || k;
}

/* ---------- Crossref 补录 ---------- */
$("#btn-cr-doi").addEventListener("click", async () => {
  if (!lastResult?.doi) return;
  try {
    const m = await API.get(`/api/v1/crossref/lookup?doi=${encodeURIComponent(lastResult.doi)}`);
    renderCandidates([m]);
  } catch (e) { toast(e.message); }
});

$("#btn-cr-search").addEventListener("click", async () => {
  const q = $("#cr-query").value.trim();
  if (!q) { toast("请输入检索关键词"); return; }
  $("#cr-candidates").innerHTML = `<div class="loading"><span class="spinner"></span>检索中…</div>`;
  try {
    const cands = await API.get(`/api/v1/crossref/search?q=${encodeURIComponent(q)}&rows=5`);
    renderCandidates(cands);
  } catch (e) {
    $("#cr-candidates").innerHTML = `<span style="color:var(--danger)">${escapeHtml(e.message)}</span>`;
  }
});

function renderCandidates(cands) {
  const box = $("#cr-candidates");
  if (!cands.length) { box.innerHTML = `<div class="loading">无结果</div>`; return; }
  box.innerHTML = cands.map((c, i) => `
    <div class="match-card">
      <div class="info">
        <div style="font-weight:600">${escapeHtml(c.title)}</div>
        <div class="match-on">
          ${c.first_author ? escapeHtml(c.first_author) : ""}${c.authors?.length > 1 ? " 等" : ""}
          ${c.year ? ` · ${c.year}` : ""}${c.journal ? ` · ${escapeHtml(c.journal)}` : ""}
          ${c.doi ? ` · ${escapeHtml(c.doi)}` : ""}
        </div>
      </div>
      <button class="btn primary" data-add="${i}">入库</button>
    </div>
  `).join("");
  box.querySelectorAll("[data-add]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const c = cands[+btn.dataset.add];
      try {
        const p = await API.post("/api/v1/papers", {
          title: c.title,
          authors: c.authors || [],
          first_author: c.first_author,
          year: c.year,
          journal: c.journal,
          volume: c.volume,
          issue: c.issue,
          pages: c.pages,
          doi: c.doi,
          abstract: c.abstract,
          source: "crossref",
        });
        toast("已入库（仅元数据，可稍后补充 PDF）");
        btn.textContent = "已入库";
        btn.disabled = true;
        setTimeout(() => { location.href = `reader-host.html?id=${p.id}`; }, 700);
      } catch (e) {
        if (e.status === 409) toast("该 DOI 已在库中");
        else toast(e.message);
      }
    });
  });
}
