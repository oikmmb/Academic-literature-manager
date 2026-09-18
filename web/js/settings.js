/** 设置页：翻译提供商选择（DeepSeek / 有道 / 百度）+ 凭据读写 + 测试。 */
const $ = (sel) => document.querySelector(sel);
const CRED_KEYS = {
  deepseek: ["deepseek_api_key", "deepseek_base_url", "deepseek_model"],
  youdao: ["youdao_app_key", "youdao_app_secret"],
  baidu: ["baidu_ak", "baidu_sk"],
};
let currentProvider = "deepseek";

function selectProvider(provider) {
  currentProvider = provider;
  document.querySelectorAll(".provider-card").forEach((c) => c.classList.toggle("active", c.id === `pc-${provider}`));
  document.querySelector(`input[name="provider"][value="${provider}"]`).checked = true;
  $("#cred-panel").style.display = "block";
  for (const p of Object.keys(CRED_KEYS)) {
    $(`#cred-${p}`).style.display = p === provider ? "" : "none";
  }
  $("#cred-title").textContent = { deepseek: "DeepSeek 凭据", youdao: "有道智云凭据", baidu: "百度翻译凭据" }[provider];
}

document.querySelectorAll('input[name="provider"]').forEach((r) => {
  r.addEventListener("change", () => selectProvider(r.value));
});

function selectChatProvider(provider) {
  const idMap = { deepseek: "cc-deepseek", openai_compat: "cc-openai" };
  document.querySelectorAll(".provider-card").forEach((c) => {
    if (c.id.startsWith("cc-")) c.classList.toggle("active", c.id === idMap[provider]);
  });
  const radio = document.querySelector(`input[name="chat-provider"][value="${provider}"]`);
  if (radio) radio.checked = true;
  $("#cc-cred").style.display = provider === "openai_compat" ? "" : "none";
}
$("#cc-deepseek").addEventListener("click", () => selectChatProvider("deepseek"));
$("#cc-openai").addEventListener("click", () => selectChatProvider("openai_compat"));

async function load() {
  const s = await API.get("/api/v1/settings");
  $("#f-ds-key").value = s.deepseek_api_key || "";
  $("#f-ds-base").value = s.deepseek_base_url || "";
  $("#f-ds-model").value = s.deepseek_model || "";
  $("#f-yd-key").value = s.youdao_app_key || "";
  $("#f-yd-secret").value = s.youdao_app_secret || "";
  $("#f-bd-ak").value = s.baidu_ak || "";
  $("#f-bd-sk").value = s.baidu_sk || "";
  selectProvider(s.translate_provider || "deepseek");
  $("#f-chat-base").value = s.chat_base_url || "";
  $("#f-chat-key").value = s.chat_api_key || "";
  $("#f-chat-model").value = s.chat_model || "";
  selectChatProvider(s.chat_provider || "deepseek");
  $("#f-hl-opacity").value = s.highlight_opacity || "0.55";
  $("#f-pdf-dir").value = s.pdf_dir || "";
  $("#pdf-dir-hint").textContent = s.pdf_dir
    ? "当前保存目录：" + s.pdf_dir
    : "留空时使用默认目录；修改后新导入的文献保存到新位置，已有文献不受影响";
}

async function save() {
  const sets = {
    translate_provider: currentProvider,
    deepseek_api_key: $("#f-ds-key").value.trim(),
    deepseek_base_url: $("#f-ds-base").value.trim(),
    deepseek_model: $("#f-ds-model").value.trim(),
    youdao_app_key: $("#f-yd-key").value.trim(),
    youdao_app_secret: $("#f-yd-secret").value.trim(),
    baidu_ak: $("#f-bd-ak").value.trim(),
    baidu_sk: $("#f-bd-sk").value.trim(),
    chat_provider: document.querySelector('input[name="chat-provider"]:checked')?.value || "deepseek",
    chat_base_url: $("#f-chat-base").value.trim(),
    chat_api_key: $("#f-chat-key").value.trim(),
    chat_model: $("#f-chat-model").value.trim(),
    highlight_opacity: $("#f-hl-opacity").value,
    pdf_dir: $("#f-pdf-dir").value.trim(),
  };
  try {
    for (const [k, v] of Object.entries(sets)) {
      if (v) await API.put(`/api/v1/settings/${k}`, { value: v });
    }
    // pdf_dir 允许空值（恢复默认目录）
    await API.put("/api/v1/settings/pdf_dir", { value: sets.pdf_dir });
    toast("设置已保存");
  } catch (e) { toast(e.message); }
}

$("#btn-save").addEventListener("click", save);

$("#btn-pdf-dir-reset").addEventListener("click", () => {
  $("#f-pdf-dir").value = "";
  $("#pdf-dir-hint").textContent = "留空时使用默认目录；修改后新导入的文献保存到新位置，已有文献不受影响";
});

$("#btn-test").addEventListener("click", async () => {
  const box = $("#test-result");
  box.textContent = "测试中…";
  await save();   // 先保存当前输入再测试
  try {
    const t0 = Date.now();
    const data = await API.post("/api/v1/translate", { text: "Deep learning has revolutionized artificial intelligence." });
    box.innerHTML = `<span class="status-ok">✓ 翻译成功（${Date.now() - t0}ms，${data.cached ? "命中缓存" : "API 调用"}）</span><br>${escapeHtml(data.translated)}`;
  } catch (e) {
    box.innerHTML = `<span class="status-err">✗ ${escapeHtml(e.message)}</span>`;
  }
});

load();
