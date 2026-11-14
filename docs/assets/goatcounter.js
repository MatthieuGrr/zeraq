/* Zeraq — statistiques de visite GoatCounter (sans cookies), compatibles navigation instantanée. */
(function () {
  "use strict";

  if (window.goatcounter) return;
  window.goatcounter = { no_onload: true };

  // count.js est servi depuis le site : les bloqueurs (et le DNS maison) filtrent gc.zgo.at.
  var script = document.createElement("script");
  script.async = true;
  script.src = document.currentScript.src.replace(/goatcounter\.js.*$/, "count.js");
  script.dataset.goatcounter = "https://georger.goatcounter.com/count";
  script.onload = function () {
    // document$ rejoue la page courante puis chaque page chargée par la navigation instantanée.
    document$.subscribe(function () {
      window.goatcounter.count({ path: location.host + location.pathname });
    });
  };
  document.head.appendChild(script);
})();
