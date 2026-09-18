/** 全局笔记（思维导图）：树布局渲染 + 节点增删改 + AI 生成。 */
const MM = {
  paperId: state.paperId,
  tree: null,
  layout: new Map(),   // node.id -> {x, y, w}（布局单位；已应用自定义位置）
  zoom: 1,             // 画布缩放
};

// 注意：$ 已在 reader.js 定义（全局词法作用域共享，重复声明会导致本脚本整体 SyntaxError）
const UNIT_W = 200;    // 叶子单位宽度
const LEVEL_H = 96;    // 层高
const NODE_W = 190;
const MM_PAD = 1500;   // 无限画布四周内边距（100% 缩放也能平移）

async function mmLoad() {
  const data = await API.get(`/api/v1/papers/${MM.paperId}/mindmap`);
  MM.tree = data.tree;
  mmRender();
}

/* ---------- 布局：自顶向下，父节点水平居中于子树 ---------- */
function mmLayout(node, depth, x0) {
  if (!node) return;
  const children = node.children || [];
  if (!children.length) {
    // 叶子也统一存渲染像素（x = 左边缘）
    MM.layout.set(node.id ?? "root", { x: x0 * UNIT_W - NODE_W / 2, y: depth * LEVEL_H, w: 1 });
    return x0 + 1;
  }
  let cx = x0;
  for (const c of children) cx = mmLayout(c, depth + 1, cx);
  const w = cx - x0;
  // 统一存渲染像素：x = 节点左边缘（居中于子树），y = 顶部
  MM.layout.set(node.id ?? "root", {
    x: (x0 + (w - 1) / 2) * UNIT_W - NODE_W / 2,
    y: depth * LEVEL_H,
    w,
  });
  return cx;
}

function mmPos(id) {
  // 布局表统一存渲染像素坐标（x=左边缘, y=顶部），叠加无限画布边距
  const p = MM.layout.get(id ?? "root");
  return { left: p.x + MM_PAD, top: p.y + MM_PAD };
}

function mmFindNode(node, id) {
  if (!node) return null;
  if (node.id === id) return node;
  for (const c of node.children || []) {
    const r = mmFindNode(c, id);
    if (r) return r;
  }
  return null;
}

/* 应用自定义位置：有 x/y 的节点覆盖自动布局，子树整体平移 */
function mmApplyCustomPositions() {
  const walk = (node, dx, dy) => {
    if (node.id != null && node.x != null && node.y != null) {
      const auto = MM.layout.get(node.id);
      if (auto) {
        dx = node.x - auto.x;
        dy = node.y - auto.y;
      }
    }
    if (node.id != null) {
      const auto = MM.layout.get(node.id);
      if (auto) MM.layout.set(node.id, { x: auto.x + dx, y: auto.y + dy, w: auto.w });
    }
    for (const c of node.children || []) walk(c, dx, dy);
  };
  if (MM.tree && MM.tree.id !== null) walk(MM.tree, 0, 0);
}

/* ---------- 渲染 ---------- */
function mmRender() {
  const canvas = $("#mm-canvas");
  if (!MM.tree || MM.tree.id === null) {
    canvas.innerHTML = `
      <div class="mm-empty">
        <div style="font-size:40px; margin-bottom:12px">🧠</div>
        <div style="margin-bottom:16px">还没有全局笔记。可以用 AI 一键梳理全文要点，或手动搭建</div>
        <button class="btn primary" id="mm-empty-ai">🤖 AI 生成思维导图</button>
        <button class="btn" id="mm-empty-manual">＋ 手动添加节点</button>
      </div>`;
    $("#mm-empty-ai").addEventListener("click", mmGenerate);
    $("#mm-empty-manual").addEventListener("click", () => mmAddNode(null, null));
    $("#mm-hint").textContent = "";
    return;
  }
  MM.layout.clear();
  mmLayout(MM.tree, 0, 0);
  mmApplyCustomPositions();
  let maxRight = 0, maxBottom = 0;
  for (const p of MM.layout.values()) {
    maxRight = Math.max(maxRight, p.x + p.w * UNIT_W + 120);
    maxBottom = Math.max(maxBottom, p.y + 80);
  }
  // 无限画布：内容四周留大边距，任何缩放级别都可平移。
  // 滚动空间由非绝对定位的 spacer 撑起（canvas 视口尺寸交给 flex，避免 flex 干扰水平滚动）

  // SVG 连线
  let svg = `<svg style="position:absolute;inset:0;width:100%;height:100%;pointer-events:none">`;
  const walk = (node) => {
    if (!node || node.id === null) return;
    const p = mmPos(node.id ?? "root");
    for (const c of node.children || []) {
      const cp = mmPos(c.id);
      const x1 = p.left + NODE_W / 2, y1 = p.top + 40;
      const x2 = cp.left + NODE_W / 2, y2 = cp.top;
      const mx = (x1 + x2) / 2;
      svg += `<path d="M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}"
        stroke="#9db2d6" stroke-width="1.5" fill="none"/>`;
      walk(c);
    }
  };
  walk(MM.tree);
  svg += "</svg>";

  const nodesHtml = [];
  const walkNodes = (node) => {
    if (!node || node.id === null) return;
    const p = mmPos(node.id ?? "root");
    const isRoot = node.parent_id === null;
    nodesHtml.push(`
      <div class="mm-node ${isRoot ? "root" : ""}" data-id="${node.id}" data-root="${isRoot}"
        style="left:${p.left}px; top:${p.top}px">
        <div class="mm-text">${escapeHtml(node.text)}</div>
        <div class="mm-ops">
          <button data-op="add" title="添加子节点">＋</button>
          <button data-op="edit" title="编辑">✎</button>
          <button data-op="del" title="删除（含子节点）">🗑</button>
        </div>
      </div>`);
    for (const c of node.children || []) walkNodes(c);
  };
  walkNodes(MM.tree);

  // zoom-wrap 必须显式尺寸：内容全是绝对定位，否则 SVG 连线 100%×100% = 0×0 不可见
  const wrapW = maxRight + MM_PAD * 2;
  const wrapH = maxBottom + MM_PAD * 2;
  canvas.innerHTML = `<div style="width:${wrapW * MM.zoom}px;height:${wrapH * MM.zoom}px"></div>`
    + `<div id="mm-zoom-wrap" style="position:absolute;top:0;left:0;width:${wrapW}px;height:${wrapH}px;transform-origin:0 0;transform:scale(${MM.zoom})">`
    + svg + nodesHtml.join("") + "</div>";

  canvas.querySelectorAll(".mm-node").forEach((el) => {
    const id = +el.dataset.id;
    el.querySelector('[data-op="add"]').addEventListener("click", (e) => {
      e.stopPropagation();
      mmAddNode(null, id);
    });
    el.querySelector('[data-op="edit"]').addEventListener("click", (e) => {
      e.stopPropagation();
      mmEditInline(el, id);
    });
    el.querySelector('[data-op="del"]').addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!confirm("删除该节点及其全部子节点？")) return;
      await API.delete(`/api/v1/mindmap/nodes/${id}`);
      mmLoad();
    });
    // 节点拖拽（仅左键；中键留给画布平移）
    el.addEventListener("mousedown", (e) => {
      if (e.button !== 0) return;
      if (e.target.closest(".mm-ops")) return;
      if (el.querySelector(".mm-text").contentEditable === "true") return;
      e.preventDefault();
      const node = mmFindNode(MM.tree, id);
      const auto = MM.layout.get(id);
      if (!node || !auto) return;
      mmDrag = {
        id, node,
        startX: e.clientX, startY: e.clientY,
        origX: node.x ?? auto.x, origY: node.y ?? auto.y,
        moved: false,
      };
    });
  });
  $("#mm-hint").textContent = "提示：左键按住节点=移动节点；左键按住空白=移动画布；Ctrl+滚轮缩放画布";
}

function mmEditInline(el, id) {
  const textEl = el.querySelector(".mm-text");
  textEl.contentEditable = "true";
  textEl.focus();
  const save = async () => {
    textEl.contentEditable = "false";
    const text = textEl.textContent.trim();
    if (text && text !== MM._findText(id)) {
      await API.put(`/api/v1/mindmap/nodes/${id}`, { text });
    }
    mmLoad();
  };
  textEl.onblur = save;
  textEl.onkeydown = (e) => {
    if (e.key === "Enter") { e.preventDefault(); save(); }
    if (e.key === "Escape") { textEl.onblur = null; mmLoad(); }
  };
}

MM._findText = (id) => {
  const walk = (n) => {
    if (!n) return null;
    if (n.id === id) return n.text;
    for (const c of n.children || []) {
      const r = walk(c);
      if (r !== null) return r;
    }
    return null;
  };
  return walk(MM.tree);
};

async function mmAddNode(text, parentId) {
  const t = text !== null ? text : prompt("节点内容：");
  if (t === null) return;
  await API.post(`/api/v1/papers/${MM.paperId}/mindmap/nodes`, { parent_id: parentId, text: t || "新节点" });
  mmLoad();
}

async function mmGenerate() {
  const btn = $("#mm-ai");
  btn.disabled = true;
  btn.textContent = "AI 梳理中…（约 10~40 秒）";
  $("#mm-hint").textContent = "";
  try {
    const data = await API.post(`/api/v1/papers/${MM.paperId}/mindmap/generate`, {});
    // 直接导入（append；无根时作为根）
    await API.post(`/api/v1/papers/${MM.paperId}/mindmap/import`, { tree: data.tree, mode: "append" });
    mmLoad();
    toast(`AI 已生成要点（${data.source_chars} 字原文）`);
  } catch (e) {
    toast(e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "🤖 AI 生成";
  }
}

/* ---------- 节点拖拽（位置持久化） ---------- */
let mmDrag = null;

document.addEventListener("mousemove", (e) => {
  if (mmDrag) {
    const dxPx = (e.clientX - mmDrag.startX) / MM.zoom;   // 像素差（除缩放系数）
    const dyPx = (e.clientY - mmDrag.startY) / MM.zoom;
    if (Math.abs(e.clientX - mmDrag.startX) > 3 || Math.abs(e.clientY - mmDrag.startY) > 3) mmDrag.moved = true;
    mmDrag.node.x = mmDrag.origX + dxPx;
    mmDrag.node.y = mmDrag.origY + dyPx;
    mmRender();   // 实时预览（子树跟随）
    return;
  }
  if (mmPan) {
    const canvas = $("#mm-canvas");
    canvas.scrollLeft = mmPan.sl - (e.clientX - mmPan.x);
    canvas.scrollTop = mmPan.st - (e.clientY - mmPan.y);
  }
});

document.addEventListener("mouseup", async () => {
  if (mmDrag) {
    const d = mmDrag;
    mmDrag = null;
    if (d.moved) {
      try {
        await API.put(`/api/v1/mindmap/nodes/${d.id}`, { x: d.node.x, y: d.node.y });
      } catch (err) { toast(err.message); }
    }
  }
  mmPan = null;
});

/* ---------- 拖拽平移画布：左键按空白处（节点上左键=移节点）；中键任意位置 ---------- */
let mmPan = null;
$("#mm-canvas").addEventListener("mousedown", (e) => {
  const onNode = e.target.closest(".mm-node");
  const panKey = e.button === 1 || (e.button === 0 && !onNode);
  if (!panKey) return;
  e.preventDefault();   // 抑制中键 autoscroll / 左键文本选择
  const canvas = $("#mm-canvas");
  mmPan = { x: e.clientX, y: e.clientY, sl: canvas.scrollLeft, st: canvas.scrollTop };
});

/* ---------- 画布缩放 ---------- */
function mmApplyZoom(anchorX, anchorY) {
  const canvas = $("#mm-canvas");
  if (anchorX != null && anchorY != null) {
    const old = MM._oldZoom || MM.zoom;
    const rect = canvas.getBoundingClientRect();
    const ox = anchorX - rect.left + canvas.scrollLeft;
    const oy = anchorY - rect.top + canvas.scrollTop;
    mmRender();
    const ratio = MM.zoom / old;
    canvas.scrollLeft = ox * ratio - (anchorX - rect.left);
    canvas.scrollTop = oy * ratio - (anchorY - rect.top);
    MM._oldZoom = MM.zoom;
  } else {
    mmRender();
  }
}

function mmZoomBy(factor, anchorX, anchorY) {
  MM.zoom = Math.min(Math.max(MM.zoom * factor, 0.4), 2.5);
  mmApplyZoom(anchorX, anchorY);
}

// 缩放监听在整个导图面板上：防止鼠标在工具栏等区域时 Ctrl+滚轮缩放整个页面
$("#mm-overlay").addEventListener("wheel", (e) => {
  if (!e.ctrlKey) return;
  e.preventDefault();
  mmZoomBy(e.deltaY < 0 ? 1.1 : 0.9, e.clientX, e.clientY);
}, { passive: false });

/* ---------- 面板开关 ---------- */
function mmOpen() {
  $("#mm-overlay").style.display = "flex";
  mmLoad().then(() => {
    // 无限画布：初始滚动到内容区（左上角 = MM_PAD 处）
    const canvas = $("#mm-canvas");
    canvas.scrollLeft = MM_PAD * MM.zoom;
    canvas.scrollTop = MM_PAD * MM.zoom;
  });
}
function mmClose() { $("#mm-overlay").style.display = "none"; }
$("#btn-mindmap").addEventListener("click", mmOpen);
$("#mm-close").addEventListener("click", mmClose);
$("#mm-ai").addEventListener("click", mmGenerate);
$("#mm-add-root").addEventListener("click", () => mmAddNode(null, null));
$("#mm-zoom-in").addEventListener("click", () => mmZoomBy(1.2));
$("#mm-zoom-out").addEventListener("click", () => mmZoomBy(1 / 1.2));
$("#mm-zoom-reset").addEventListener("click", () => { MM.zoom = 1; mmApplyZoom(); });
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && $("#mm-overlay").style.display === "flex") mmClose();
});

// URL 带 mindmap=1 时自动打开导图（调试/快捷入口）
if (new URLSearchParams(location.search).get("mindmap")) mmOpen();
