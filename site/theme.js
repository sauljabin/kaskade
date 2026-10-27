"use strict";

// Loaded before the stylesheet applies, so a saved theme never flashes. Without
// a saved choice, the page follows the system's color scheme.
(() => {
  const key = "theme";
  const query = window.matchMedia("(prefers-color-scheme: light)");

  function saved() {
    try {
      return window.localStorage.getItem(key);
    } catch {
      return null;
    }
  }

  function current() {
    return document.documentElement.dataset.theme ?? (query.matches ? "light" : "dark");
  }

  function apply(theme) {
    if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
    else delete document.documentElement.dataset.theme;
  }

  // Choosing the system's scheme forgets the choice, so the page follows the
  // system again.
  function choose(theme) {
    const system = query.matches ? "light" : "dark";
    try {
      if (theme === system) window.localStorage.removeItem(key);
      else window.localStorage.setItem(key, theme);
    } catch {
      // Storage blocked: the choice lasts until the page closes.
    }
    apply(theme === system ? null : theme);
  }

  function setUpToggle() {
    const button = document.querySelector("[data-theme-toggle]");
    if (!button) return;
    const label = button.querySelector("[data-theme-label]");
    const render = () => {
      const next = current() === "dark" ? "light" : "dark";
      label.textContent = `Switch to ${next} theme`;
      button.title = label.textContent;
    };
    button.hidden = false;
    button.addEventListener("click", () => {
      choose(current() === "dark" ? "light" : "dark");
      render();
    });
    query.addEventListener("change", render);
    render();
  }

  apply(saved());
  document.addEventListener("DOMContentLoaded", setUpToggle);
})();
