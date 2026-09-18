/** 参考文献悬停提示：鼠标在正文引用序号上停留 2 秒 → 悬浮窗显示对应条目。
 *  支持 [88]、[88-90]、[88,89,90]、[88]-[90]、[88]–[90] 等格式（自动展开范围）。
 *  注意：$ / state / smartJoin / pagePointFromClient / wordIndexAtPoint 复用 reader.js。 */
let refTimer = null, refLastPos = null, refTip = null;

function refExtractNums(text) {
  const nums = new Set();
  const addRange = (a, b) => {
    for (let n = +a; n <= Math.min(+b, +a + 50); n++) nums.add(n);
  };
  // [88]
  for (const m of text.matchAll(/\[(\d{1,3})\]/g)) nums.add(+m[1]);
  // [88-90] / [88–90]
  for (const m of text.matchAll(/\[(\d{1,3})\s*[-–—]\s*(\d{1,3})\]/g)) addRange(m[1], m[2]);
  // [88] - [90] 跨括号范围
  for (const m of text.matchAll(/\[(\d{1,3})\]\s*[-–—]\s*\[(\d{1,3})\]/g)) addRange(m[1], m[2]);
  return [...nums].slice(0, 20);
}

function refHideTip() {
  if (refTip) { refTip.remove(); refTip = null; }
}

async function refCheckHover(pos) {
  const el = document.elementFromPoint(pos.x, pos.y)?.closest?.(".page-wrap");
  if (!el) return;
  const words = state.words.get(+el.dataset.page) || [];
  if (!words.length) return;
  const p = pagePointFromClient(el, pos.x, pos.y);
  const wi = wordIndexAtPoint(words, p.x, p.y);
  if (wi < 0) return;
  const windowWords = words.slice(Math.max(0, wi - 12), wi + 13).map((w) => w.t);
  const nums = refExtractNums(smartJoin(windowWords));
  if (!nums.length) return;
  try {
    const data = await API.get(`/api/v1/papers/${state.paperId}/references?nums=${nums.join(",")}`);
    if (!data.items.length) return;
    refShowTip(pos, data.items);
  } catch (e) { /* 解析失败静默 */ }
}

function refShowTip(pos, items) {
  refHideTip();
  refTip = document.createElement("div");
  refTip.id = "ref-tip";
  refTip.innerHTML = items.map((it) => `
    <div class="ref-item"><b>[${it.num}]</b> ${escapeHtml(it.text)}</div>`).join("");
  document.body.appendChild(refTip);
  const tw = refTip.offsetWidth, th = refTip.offsetHeight;
  let x = pos.x + 14, y = pos.y + 16;
  if (x + tw > window.innerWidth - 8) x = Math.max(8, pos.x - tw - 14);
  if (y + th > window.innerHeight - 8) y = Math.max(8, window.innerHeight - th - 8);
  refTip.style.left = `${x}px`;
  refTip.style.top = `${y}px`;
}

document.addEventListener("mousemove", (e) => {
  if (refTip) return;   // 悬浮窗显示期间：鼠标移动不隐藏、不触发新的悬停检测
  if (!e.target.closest?.(".textlayer")) { clearTimeout(refTimer); refTimer = null; return; }
  refLastPos = { x: e.clientX, y: e.clientY };
  clearTimeout(refTimer);
  refTimer = setTimeout(() => refCheckHover(refLastPos), 2000);
});

// 仅点击悬浮窗外区域才关闭（悬浮窗内点击 = 滚动查看长内容，不关）
document.addEventListener("mousedown", (e) => {
  if (!refTip) return;
  if (e.target.closest?.("#ref-tip")) return;
  refHideTip();
});
