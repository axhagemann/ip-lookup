// Theme toggle. Every page starts in the OS theme, which CSS applies on its own
// (prefers-color-scheme), so there is no flash to prevent. A click overrides it
// for this page view only — nothing is stored, by design: switching away from
// the OS look is a deliberate per-visit choice.
(function () {
  var root = document.documentElement;
  var media = window.matchMedia("(prefers-color-scheme: dark)");
  var btn = document.querySelector(".theme-toggle");
  if (!btn) return;

  function isDark() {
    var forced = root.getAttribute("data-theme");
    return forced ? forced === "dark" : media.matches;
  }

  function sync() {
    btn.setAttribute("aria-pressed", isDark() ? "true" : "false");
  }

  btn.addEventListener("click", function () {
    root.setAttribute("data-theme", isDark() ? "light" : "dark");
    sync();
  });

  // Keeps aria-pressed honest if the OS theme flips while nothing is forced.
  media.addEventListener("change", sync);

  sync();
  btn.hidden = false;
})();
