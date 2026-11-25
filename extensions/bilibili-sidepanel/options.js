import { APP_TARGET_KEY, loadAppTarget, normalizeAppTarget } from "./app-target.js";

const form = document.querySelector("#target");
const status = document.querySelector("#status");

form.elements.target.value = await loadAppTarget(chrome);
form.addEventListener("change", async () => {
  await chrome.storage.local.set({ [APP_TARGET_KEY]: normalizeAppTarget(form.elements.target.value) });
  status.textContent = "已保存，已打开的侧边栏会自动切换。";
});
