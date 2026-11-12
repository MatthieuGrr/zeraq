/* Zeraq — favoris locaux (localStorage), compatibles navigation instantanée. */
(function () {
  "use strict";

  var STORE_KEY = "zeraq:favoris";
  var VEILLE_PATH = /\/\d{4}\/\d{2}\/\d{4}-\d{2}-\d{2}\/?(index\.html)?$/;

  function load() {
    try {
      var data = JSON.parse(localStorage.getItem(STORE_KEY) || "{}");
      return data && typeof data === "object" ? data : {};
    } catch (e) {
      return {};
    }
  }

  function save(data) {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(data));
    } catch (e) {
      /* stockage indisponible (navigation privée stricte) : on ignore */
    }
  }

  function pagePath() {
    return location.pathname.replace(/index\.html$/, "");
  }

  function headingTitle(h2) {
    var clone = h2.cloneNode(true);
    clone.querySelectorAll(".headerlink, .fav-star").forEach(function (n) {
      n.remove();
    });
    return clone.textContent.trim();
  }

  function pageTitle() {
    var h1 = document.querySelector(".md-content h1");
    return h1 ? headingTitle(h1) : document.title;
  }

  function setStar(btn, on) {
    btn.textContent = on ? "⭐" : "☆";
    btn.classList.toggle("fav-star--on", on);
    btn.setAttribute("aria-pressed", on ? "true" : "false");
    btn.title = on ? "Retirer des favoris" : "Ajouter aux favoris";
    btn.setAttribute("aria-label", btn.title);
  }

  function decorateVeille() {
    if (!VEILLE_PATH.test(location.pathname)) return;
    var favs = load();
    document.querySelectorAll(".md-content article h2[id]").forEach(function (h2) {
      if (h2.querySelector(".fav-star")) return;
      var key = pagePath() + "#" + h2.id;
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "fav-star";
      setStar(btn, !!favs[key]);
      btn.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        var data = load();
        if (data[key]) {
          delete data[key];
          setStar(btn, false);
        } else {
          data[key] = {
            titre: headingTitle(h2),
            page: pageTitle(),
            url: key,
            ajoute: new Date().toISOString()
          };
          setStar(btn, true);
        }
        save(data);
      });
      h2.appendChild(btn);
    });
  }

  function renderFavoris() {
    var root = document.getElementById("favoris-locaux");
    if (!root) return;
    var data = load();
    var items = Object.keys(data).map(function (k) {
      return data[k];
    });
    items.sort(function (a, b) {
      return (b.url || "").localeCompare(a.url || "");
    });
    root.innerHTML = "";
    if (!items.length) {
      var p = document.createElement("p");
      p.className = "fav-empty";
      p.textContent =
        "Aucun favori enregistré sur cet appareil. Cliquer sur ☆ à côté d'une actu pour l'ajouter.";
      root.appendChild(p);
      return;
    }
    var ul = document.createElement("ul");
    ul.className = "fav-list";
    items.forEach(function (item) {
      var li = document.createElement("li");
      var a = document.createElement("a");
      a.href = item.url;
      a.textContent = item.titre;
      var meta = document.createElement("span");
      meta.className = "fav-meta";
      meta.textContent = " — " + item.page;
      var rm = document.createElement("button");
      rm.type = "button";
      rm.className = "md-button fav-remove";
      rm.textContent = "Retirer";
      rm.addEventListener("click", function () {
        var d = load();
        delete d[item.url];
        save(d);
        renderFavoris();
      });
      li.appendChild(a);
      li.appendChild(meta);
      li.appendChild(rm);
      ul.appendChild(li);
    });
    root.appendChild(ul);
  }

  function init() {
    decorateVeille();
    renderFavoris();
  }

  if (typeof document$ !== "undefined" && document$.subscribe) {
    document$.subscribe(init);
  } else if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
