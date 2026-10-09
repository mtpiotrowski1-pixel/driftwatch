// Apply the saved palette and language before first paint to avoid a flash.
// Kept as an external same-origin script so the Content-Security-Policy can
// forbid inline script (script-src 'self').
(function () {
  try {
    var theme = localStorage.getItem("driftwatch_theme");
    if (theme && theme !== "indigo") document.documentElement.dataset.theme = theme;
    var lang = localStorage.getItem("driftwatch_lang");
    document.documentElement.lang = lang === "en" || lang === "pl"
      ? lang
      : navigator.language.toLowerCase().startsWith("pl") ? "pl" : "en";
  } catch (error) {
    /* private mode or storage disabled — fall back to defaults */
  }
})();
