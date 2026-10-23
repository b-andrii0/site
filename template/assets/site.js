/* Cursus-site: kopiëren, zoeken, thema, menu, inhoudstafel. Geen externe bronnen. */
(function () {
  "use strict";
  var doc = document.documentElement;

  /* ---------- toast ---------- */
  var toast = document.getElementById("toast"), toastTimer;
  function melding(html) {
    toast.innerHTML = html;
    toast.classList.add("zichtbaar");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toast.classList.remove("zichtbaar"); }, 2600);
  }
  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; });
  }

  /* ---------- eigen initialen in plaats van XX (alleen in wat je kopieert) ---------- */
  function leesInit() { try { return (localStorage.getItem("initialen") || "").trim(); } catch (e) { return ""; } }
  function metInitialen(s) {
    var v = leesInit();
    if (!v) return s;
    return String(s).replace(/\b(server|client)XX\b/gi, function (m, p) { return p + v; });
  }

  /* ---------- kopiëren ---------- */
  function kopieer(tekst) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(tekst).catch(function () { return oudeManier(tekst); });
    }
    return Promise.resolve(oudeManier(tekst));
  }
  function oudeManier(tekst) {
    var ta = document.createElement("textarea");
    ta.value = tekst; ta.setAttribute("readonly", "");
    ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); } finally { document.body.removeChild(ta); }
  }
  document.addEventListener("click", function (e) {
    var b = e.target.closest(".kopieer");
    if (!b) return;
    var blok = b.closest(".blok");
    var toestel = b.getAttribute("data-toestel") || (blok && blok.getAttribute("data-toestel")) || "?";
    var tekst = metInitialen(b.getAttribute("data-copy"));
    toestel = metInitialen(toestel);
    kopieer(tekst).then(function () {
      b.classList.add("ok"); b.textContent = "Gekopieerd";
      setTimeout(function () { b.classList.remove("ok"); b.textContent = "Kopieer"; }, 1600);
      if (toestel === "bestand" || toestel === "Bestandsinhoud") melding("Gekopieerd — inhoud voor het bestand");
      else melding("Gekopieerd — uitvoeren op: <b>" + esc(toestel) + "</b>");
    });
  });

  /* ---------- thema ---------- */
  function huidigDonker() {
    var t = doc.getAttribute("data-thema");
    if (t) return t === "donker";
    return window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches;
  }
  var tk = document.querySelector(".thema-knop");
  if (tk) tk.addEventListener("click", function () {
    var nieuw = huidigDonker() ? "licht" : "donker";
    doc.setAttribute("data-thema", nieuw);
    try { localStorage.setItem("thema", nieuw); } catch (e) {}
  });

  /* ---------- stijlkiezer (alleen in voorbeeldmodus) ---------- */
  document.querySelectorAll("[data-zet-stijl]").forEach(function (b) {
    b.addEventListener("click", function () {
      var s = b.getAttribute("data-zet-stijl");
      doc.setAttribute("data-stijl", s);
      try { localStorage.setItem("stijl", s); } catch (e) {}
      melding("Stijl " + b.textContent + ": <b>" + { werkboek: "Werkboek", blauwdruk: "Blauwdruk", signaal: "Signaal" }[s] + "</b>");
    });
  });

  /* ---------- menu (mobiel) ---------- */
  var mk = document.querySelector(".menu-knop"), sluier = document.querySelector(".sluier");
  function menu(open) {
    document.body.classList.toggle("menu-open", open);
    mk.setAttribute("aria-expanded", open ? "true" : "false");
    sluier.hidden = !open;
  }
  if (mk) mk.addEventListener("click", function () { menu(!document.body.classList.contains("menu-open")); });
  if (sluier) sluier.addEventListener("click", function () { menu(false); });

  /* ---------- boom in-/uitklappen ---------- */
  document.addEventListener("click", function (e) {
    var k = e.target.closest(".klap");
    // klik op het huidige hoofdstuk zelf: in-/uitklappen in plaats van de pagina opnieuw laden
    var huidig = e.target.closest('.hoofdstukken > li.tak > .rij > a[aria-current="page"]');
    if (huidig) { e.preventDefault(); k = huidig.parentElement.querySelector(".klap"); }
    if (!k) return;
    var li = k.closest("li.tak");
    var open = !li.classList.contains("open");
    li.classList.toggle("open", open);
    k.setAttribute("aria-expanded", open ? "true" : "false");
  });
  function openOuders(el) {
    var li = el.closest("li.tak");
    while (li) {
      li.classList.add("open");
      var k = li.querySelector(":scope > .rij > .klap");
      if (k) k.setAttribute("aria-expanded", "true");
      li = li.parentElement && li.parentElement.closest("li.tak");
    }
  }

  /* ---------- actieve sectie (rechts én in de zijbalk) ---------- */
  var tocLinks = Array.prototype.slice.call(document.querySelectorAll('.toc a[href^="#"], .zijbalk a[href^="#"]'));
  if (tocLinks.length && "IntersectionObserver" in window) {
    var map = {};
    tocLinks.forEach(function (a) { var id = a.getAttribute("href").slice(1); (map[id] = map[id] || []).push(a); });
    var koppen = Object.keys(map).map(function (id) { return document.getElementById(id); }).filter(Boolean);
    var vorige = null;
    var io = new IntersectionObserver(function () {
      var actief = null;
      for (var i = 0; i < koppen.length; i++) {
        if (koppen[i].getBoundingClientRect().top < window.innerHeight * 0.3) actief = koppen[i].id;
      }
      if (actief === vorige) return;
      vorige = actief;
      tocLinks.forEach(function (a) { a.classList.remove("actief"); });
      (map[actief] || []).forEach(function (a) {
        a.classList.add("actief");
        openOuders(a.parentElement);
        var box = a.closest(".rechts, .zijbalk"), r = a.getBoundingClientRect(), br = box && box.getBoundingClientRect();
        if (br && (r.top < br.top + 40 || r.bottom > br.bottom - 20)) box.scrollTop += r.top - br.top - br.height / 3;
      });
    }, { rootMargin: "0px 0px -60% 0px" });
    koppen.forEach(function (k) { io.observe(k); });
  }

  /* ---------- zoeken ---------- */
  var veld = document.getElementById("zoekveld"), res = document.getElementById("zoekres");
  var idx = window.ZOEKINDEX || [];
  function norm(s) {
    return String(s).toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  }
  idx.forEach(function (it) { it._h = norm(it.h); it._x = norm(it.x); it._k = norm(it.k); });
  var gekozen = -1;

  function fragment(tekst, ntekst, term) {
    var p = ntekst.indexOf(term);
    if (p < 0) return esc(tekst.slice(0, 140)) + (tekst.length > 140 ? "…" : "");
    var s = Math.max(0, p - 60), e = Math.min(tekst.length, p + term.length + 80);
    return (s > 0 ? "…" : "") + esc(tekst.slice(s, p)) + "<mark>" + esc(tekst.slice(p, p + term.length)) + "</mark>" +
      esc(tekst.slice(p + term.length, e)) + (e < tekst.length ? "…" : "");
  }
  function cmdRegel(it, term) {
    var regels = it.k.split("\n");
    for (var i = 0; i < regels.length; i++) {
      var n = norm(regels[i]), p = n.indexOf(term);
      if (p >= 0) {
        var r = regels[i];
        return esc(r.slice(0, p)) + "<mark>" + esc(r.slice(p, p + term.length)) + "</mark>" + esc(r.slice(p + term.length));
      }
    }
    return null;
  }
  function zoek(q) {
    var nq = norm(q).trim();
    if (nq.length < 2) { res.hidden = true; res.innerHTML = ""; return; }
    var woorden = nq.split(/\s+/);
    var hits = [];
    idx.forEach(function (it) {
      var score = 0, ok = true;
      woorden.forEach(function (w) {
        var s = 0;
        if (it._h.indexOf(w) >= 0) s += 10;
        if (it._k.indexOf(w) >= 0) s += 6;
        if (it._x.indexOf(w) >= 0) s += 3;
        if (!s) ok = false;
        score += s;
      });
      if (it._k.indexOf(nq) >= 0) score += 8;
      if (it._x.indexOf(nq) >= 0) score += 4;
      if (ok) hits.push({ it: it, s: score });
    });
    hits.sort(function (a, b) { return b.s - a.s || a.it.c - b.it.c; });
    hits = hits.slice(0, 30);
    gekozen = -1;
    if (!hits.length) {
      res.innerHTML = '<div class="leeg">Geen resultaten voor “' + esc(q) + '”.</div>';
    } else {
      var term = woorden[0];
      res.innerHTML = hits.map(function (h) {
        var it = h.it, k = it._k.indexOf(nq) >= 0 ? cmdRegel(it, nq) : cmdRegel(it, term);
        var x = it._x.indexOf(nq) >= 0 ? fragment(it.x, it._x, nq) : fragment(it.x, it._x, term);
        var u = it.u.split("#"), url = u[0] + "?q=" + encodeURIComponent(q.trim()) + (u[1] ? "#" + u[1] : "");
        return '<a role="option" href="' + url + '"><div class="zr-c">Hoofdstuk ' + it.c + " · " + esc(it.ct) + "</div>" +
          '<div class="zr-h">' + esc(it.h) + "</div>" +
          (k ? '<div class="zr-k">' + k + "</div>" : '<div class="zr-x">' + x + "</div>") + "</a>";
      }).join("");
    }
    res.hidden = false;
  }
  if (veld) {
    var t;
    veld.addEventListener("input", function () { clearTimeout(t); t = setTimeout(function () { zoek(veld.value); }, 90); });
    veld.addEventListener("focus", function () { if (veld.value.trim().length > 1) zoek(veld.value); });
    veld.addEventListener("keydown", function (e) {
      var items = res.querySelectorAll("a");
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (!items.length) return;
        gekozen = (gekozen + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
        items.forEach(function (a, i) { a.classList.toggle("actief", i === gekozen); });
        items[gekozen].scrollIntoView({ block: "nearest" });
      } else if (e.key === "Enter") {
        var a = items[gekozen >= 0 ? gekozen : 0];
        if (a) { e.preventDefault(); location.href = a.getAttribute("href"); res.hidden = true; }
      } else if (e.key === "Escape") {
        res.hidden = true; veld.blur();
      }
    });
    document.addEventListener("click", function (e) {
      if (!e.target.closest(".zoek")) res.hidden = true;
      if (e.target.closest(".zoek-res a")) res.hidden = true;
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "/" && document.activeElement !== veld && !/input|textarea/i.test(document.activeElement.tagName)) {
        e.preventDefault(); veld.focus(); veld.select();
      }
    });
  }

  /* ---------- menu sluiten na klik op link ---------- */
  document.querySelectorAll(".zijbalk a").forEach(function (a) { a.addEventListener("click", function () { menu(false); }); });
})();
