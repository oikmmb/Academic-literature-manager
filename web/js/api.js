/** fetch 封装：envelope 解包、错误提示、keepalive 支持（自动保存崩溃兜底用）。 */
const API = {
  async request(method, path, body, opts = {}) {
    const init = { method, headers: {}, ...opts };
    if (body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }
    if (opts.keepalive) init.keepalive = true;
    const resp = await fetch(path, init);
    let payload = null;
    try { payload = await resp.json(); } catch (e) { /* 非 JSON 响应 */ }
    if (!resp.ok) {
      const err = new Error(payload?.msg || `请求失败 (${resp.status})`);
      err.status = resp.status;
      throw err;
    }
    return payload?.data;
  },
  get(path, opts) { return this.request("GET", path, undefined, opts); },
  post(path, body, opts) { return this.request("POST", path, body, opts); },
  put(path, body, opts) { return this.request("PUT", path, body, opts); },
  delete(path, opts) { return this.request("DELETE", path, undefined, opts); },
  async upload(path, formData) {
    const resp = await fetch(path, { method: "POST", body: formData });
    let payload = null;
    try { payload = await resp.json(); } catch (e) { /* 非 JSON */ }
    if (!resp.ok) throw new Error(payload?.msg || `上传失败 (${resp.status})`);
    return payload?.data;
  },
};

function toast(msg, ms = 2200) {
  let el = document.querySelector(".toast");
  if (!el) {
    el = document.createElement("div");
    el.className = "toast";
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.remove("show"), ms);
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
