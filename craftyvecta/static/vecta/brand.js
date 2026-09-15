// CraftyVecta: shows that this Crafty runs with vecta. Crafty's own logo and
// credits stay. Where Crafty's markup has changed, nothing is added.
(function () {
  "use strict";

  var script = document.currentScript;
  var domain = script ? script.getAttribute("data-domain") : "";
  var statusUrl = script ? script.getAttribute("data-status-url") : "";
  var base = script ? script.src.replace(/brand\.js(\?.*)?$/, "") : "/static/assets/vecta/";

  function el(tag, className, text) {
    var e = document.createElement(tag);
    if (className) e.className = className;
    if (text) e.textContent = text;
    return e;
  }

  function badge(variant) {
    var b = el(statusUrl ? "a" : "span", "vecta-badge vecta-badge-" + variant);
    if (statusUrl) {
      b.href = statusUrl;
      b.target = "_blank";
      b.rel = "noopener";
    }
    b.title = domain ? "Players join through vecta at " + domain : "Players join through vecta";
    b.appendChild(el("span", "vecta-badge-with", "with"));
    var logo = el("img", "vecta-badge-logo");
    // Loads the vecta logo from Kilian's logo repository
    logo.src = "https://logo.kiliansen.de/vecta/small_dark.svg";
    logo.alt = "";
    b.appendChild(logo);
    b.appendChild(el("span", "vecta-badge-name", "vecta"));
    return b;
  }

  function footerLine(container) {
    var line = el("span", "vecta-footer text-muted d-block text-center text-sm-left");
    line.appendChild(document.createTextNode("Players join through "));
    var link = el("a", null, "vecta");
    link.href = "https://github.com/KilianSen/vecta";
    link.target = "_blank";
    link.rel = "noopener";
    line.appendChild(link);
    if (domain) {
      line.appendChild(document.createTextNode(" at "));
      var join = el(statusUrl ? "a" : "strong", null, domain);
      if (statusUrl) {
        join.href = statusUrl;
        join.target = "_blank";
        join.rel = "noopener";
      }
      line.appendChild(join);
    }
    line.appendChild(document.createTextNode("."));
    container.appendChild(line);
  }

  function run() {
    if (document.querySelector(".vecta-badge, .vecta-footer")) return;
    var navbarLogo = document.querySelector(".navbar-brand.brand-logo");
    if (navbarLogo) navbarLogo.insertAdjacentElement("afterend", badge("navbar"));
    var loginLogo = document.querySelector(".auto-form-logo");
    if (loginLogo) loginLogo.appendChild(badge("login"));
    var footer = document.querySelector("footer.footer .container-fluid");
    if (footer) footerLine(footer);
    if (document.title && document.title.indexOf("vecta") === -1) document.title += " · vecta";
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();
