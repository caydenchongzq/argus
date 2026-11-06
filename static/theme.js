/* Apply the saved theme before first paint. No saved choice follows the OS. */
(function (w) {
  var LIGHT_ICON = "/static/argus-brand/assets/logo/favicon-32.png";
  var DARK_ICON = "/static/argus-brand/assets/logo/favicon-dark-32.png";
  var AUTO_ICON = "/static/argus-brand/assets/logo/favicon.svg";

  function applyTheme(choice, persist) {
    var d = document.documentElement;
    if (choice !== "light" && choice !== "dark") choice = "system";
    if (choice === "system") d.removeAttribute("data-theme");
    else d.setAttribute("data-theme", choice);
    if (persist) localStorage.setItem("argus-theme", choice);
    var link = document.querySelector("link[data-argus-favicon]");
    if (link) {
      if (choice === "light") {
        link.href = LIGHT_ICON;
        link.type = "image/png";
      } else if (choice === "dark") {
        link.href = DARK_ICON;
        link.type = "image/png";
      } else {
        link.href = AUTO_ICON;
        link.type = "image/svg+xml";
      }
    }
    return choice;
  }

  function applyDensity(density, persist) {
    var v = density === "compact" ? "compact" : "comfortable";
    document.documentElement.setAttribute("data-density", v);
    if (persist) localStorage.setItem("argus-density", v);
    return v;
  }

  var savedTheme = localStorage.getItem("argus-theme");
  applyTheme(savedTheme || "system", false);
  applyDensity(localStorage.getItem("argus-density") || "comfortable", false);

  w.argusSetTheme = function (choice) { return applyTheme(choice, true); };
  w.argusSetDensity = function (density) { return applyDensity(density, true); };
})(window);
