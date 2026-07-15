export function applyThemeClass(theme) {
  const classes = ["theme-default","theme-bluegreyblack","theme-bluegold","theme-greenred","theme-tealslate","theme-indigoamber"];
  document.body.classList.remove(...classes);
  if (theme && theme !== "default") document.body.classList.add(`theme-${theme}`);
}
export function broadcastBrandingChanged() {
  try { localStorage.setItem("branding:lastUpdate", String(Date.now())); } catch {}
  window.dispatchEvent(new CustomEvent("branding:changed"));
}
