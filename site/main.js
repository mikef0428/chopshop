(function () {
  var cfg = window.CHOPSHOP || {};

  function lookup(key) {
    var v = cfg.links && cfg.links[key];
    return v || cfg[key] || "";
  }

  document.querySelectorAll("[data-link]").forEach(function (el) {
    var url = lookup(el.dataset.link);
    if (url) {
      el.setAttribute("href", url);
    } else {
      el.removeAttribute("href");
      el.setAttribute("aria-disabled", "true");
      el.classList.add("disabled");
      el.textContent = "Coming soon";
    }
  });

  if (cfg.contactEmail) {
    document.querySelectorAll("[data-contact]").forEach(function (el) {
      var a = document.createElement("a");
      a.href = "mailto:" + cfg.contactEmail;
      a.textContent = cfg.contactEmail;
      el.replaceChildren(a);
    });
  }

  if (!(cfg.examples && cfg.examples.length)) {
    document.querySelectorAll('[data-requires="examples"]').forEach(function (el) {
      el.remove();
    });
  }
})();
