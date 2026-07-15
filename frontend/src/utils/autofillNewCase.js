// Frontend auto-fill for "New Case" dialog
// - Fetches /api/cases/suggest_name
// - Inserts suggestion into "eDiscovery Case Name" input if empty
// - Respects user typing; does not overwrite
// - Includes Authorization header if a token is stored

(function () {
  const API = "/api/cases/suggest_name";

  function getToken() {
    try {
      // Common patterns used in this app: localStorage token or access_token
      const raw = /* removed-token-storage */ null || /* removed-token-storage */ null;
      if (!raw) return null;
      // If it's already a JWT, return it
      if (/^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+$/.test(raw)) return raw;
      // Otherwise try JSON
      try {
        const obj = JSON.parse(raw);
        return obj.access_token || obj.token || null;
      } catch {
        return raw;
      }
    } catch {
      return null;
    }
  }

  function isVisible(el) {
    if (!el) return false;
    try {
      const style = getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden") return false;
      // offsetParent is null for display:none or detached nodes (ignore fixed positioned elements by checking rect)
      const rect = el.getBoundingClientRect?.();
      if (rect && rect.width === 0 && rect.height === 0) return false;
      return true;
    } catch {
      return false;
    }
  }

  function findCaseNameInput() {
    // Be strict: only target the known case modal field to avoid filling the wrong input.
    const form = document.querySelector("#case-modal-form");
    if (!form || !isVisible(form)) return null;

    // Preferred selector used by the app.
    const byName = form.querySelector('input[name="name"]');
    if (byName) return byName;

    // Fallback: label-based lookup for "eDiscovery Case Name" (still scoped to the modal form).
    const labels = Array.from(form.querySelectorAll("label"));
    for (const label of labels) {
      const text = (label.textContent || "").toLowerCase();
      if (text.includes("ediscovery case name")) {
        const input = label.querySelector("input");
        if (input) return input;
      }
    }

    return null;
  }

  function isUserTyping(input) {
    return !!(input && input.value && input.value.trim().length > 0);
  }

  async function tryFill() {
    const input = findCaseNameInput();
    if (!input || isUserTyping(input)) return;

    const headers = {};
    const tok = getToken();
    if (tok) headers["Authorization"] = "Bearer " + tok;

    try {
      const res = await fetch(API, { credentials: 'include',  headers });
      if (!res.ok) return; // respect auth or server responses
      let data = null;
      try {
        data = await res.json();
      } catch {}
      const suggestion = (data && (data.suggested_name || data.name)) || null;
      if (suggestion && !isUserTyping(input)) {
        input.value = suggestion;
        // Notify controlled components
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
      }
    } catch (e) {
      // quiet fail
    }
  }

  // Observe DOM changes to catch the moment the modal appears
  const mo = new MutationObserver(() => {
    // defer slightly to let inner elements render
    setTimeout(tryFill, 0);
  });
  mo.observe(document.documentElement, { childList: true, subtree: true });

  // Also react to clicking a "New Case" button/link
  document.addEventListener("click", (e) => {
    const btn = e.target && (e.target.closest("button") || e.target.closest("a"));
    if (!btn) return;
    const txt = (btn.textContent || "").toLowerCase();
    if (txt.includes("new case")) {
      setTimeout(tryFill, 50);
    }
  });

  // Run once on load in case modal is already in DOM
  window.addEventListener("load", tryFill);
})();
