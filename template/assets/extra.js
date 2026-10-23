/* Extra's: weergave (alleen commando's, filter op toestel, initialen), afdrukken,
   leesvoortgang, naar boven, verder lezen, zoekhits markeren, lightbox. Geen externe bronnen. */
(function () {
  "use strict";
  function lees(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function schrijf(k, v) { try { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) {} }
  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; });
  }
  var inhoud = document.querySelector(".inhoud");
  var pagina = location.pathname.split("/").pop() || "index.html";

  /* ---------- alleen commando's + filter op toestel ---------- */
  var knopAlleen = document.getElementById("alleen-cmd");
  var chips = Array.prototype.slice.call(document.querySelectorAll(".wg-chip"));
  var APPARAAT = { server: 1, client: 1, container: 1, win: 1, browser: 1 };
  function pasToe() {
    var alleen = lees("alleenCmd") === "1", filter = lees("filter") || "alle";
    document.body.classList.toggle("alleen-cmd", alleen);
    if (knopAlleen) knopAlleen.setAttribute("aria-pressed", alleen ? "true" : "false");
    chips.forEach(function (c) { c.classList.toggle("actief", c.getAttribute("data-filter") === filter); });
    if (!inhoud) return;
    inhoud.querySelectorAll(".blok").forEach(function (b) {
      var s = b.getAttribute("data-soort");
      b.classList.toggle("verborgen", filter !== "alle" && !!APPARAAT[s] && s !== filter);
    });
    // kopjes zonder zichtbaar commando verbergen zodra er gefilterd wordt
    inhoud.querySelectorAll(":scope > h2, :scope > h3, :scope > h4, :scope > h5").forEach(function (h) {
      h.classList.remove("leeg-na-filter");
      if (!alleen && filter === "alle") return;
      var niv = +h.tagName.charAt(1), heeft = false;
      for (var el = h.nextElementSibling; el && !heeft; el = el.nextElementSibling) {
        if (/^H[2-5]$/.test(el.tagName) && +el.tagName.charAt(1) <= niv) break;
        var bl = el.matches(".blok") ? [el] : el.querySelectorAll(".blok");
        for (var i = 0; i < bl.length; i++) if (!bl[i].classList.contains("verborgen")) { heeft = true; break; }
      }
      if (!heeft) h.classList.add("leeg-na-filter");
    });
    if (alleen) inhoud.querySelectorAll("details.afb-cmds").forEach(function (d) { d.open = true; });
  }
  if (knopAlleen) knopAlleen.addEventListener("click", function () {
    schrijf("alleenCmd", lees("alleenCmd") === "1" ? null : "1"); pasToe();
  });
  chips.forEach(function (c) {
    c.addEventListener("click", function () {
      var f = c.getAttribute("data-filter"); schrijf("filter", f === "alle" ? null : f); pasToe();
    });
  });
  pasToe();

  /* ---------- initialen (gebruikt door site.js bij het kopiëren) ---------- */
  var init = document.getElementById("initialen");
  if (init) {
    init.value = lees("initialen") || "";
    init.addEventListener("input", function () {
      var v = init.value.replace(/[^A-Za-z0-9_-]/g, "");
      if (v !== init.value) init.value = v;
      schrijf("initialen", v || null);
    });
  }

  /* ---------- afdrukken / PDF ---------- */
  var dicht = [];
  window.addEventListener("beforeprint", function () {
    dicht = [];
    document.querySelectorAll("details").forEach(function (d) { if (!d.open) { dicht.push(d); d.open = true; } });
  });
  window.addEventListener("afterprint", function () { dicht.forEach(function (d) { d.open = false; }); });
  var druk = document.getElementById("afdrukken");
  if (druk) druk.addEventListener("click", function () { window.print(); });

  /* ---------- leesvoortgang, naar boven, leesplek bewaren ---------- */
  var balk = document.querySelector(".leesbalk span"), boven = document.querySelector(".naar-boven");
  var koppen = inhoud ? Array.prototype.slice.call(inhoud.querySelectorAll("h2[id], h3[id], h4[id], h5[id]")) : [];
  var bewaarTimer;
  function opScroll() {
    var h = document.documentElement.scrollHeight - innerHeight;
    if (balk) balk.style.width = (h > 0 ? Math.min(100, scrollY / h * 100) : 0) + "%";
    if (boven) boven.hidden = scrollY < 700;
    clearTimeout(bewaarTimer);
    bewaarTimer = setTimeout(function () {
      if (pagina === "index.html" || scrollY < 200) return;
      var akt = null;
      for (var i = 0; i < koppen.length; i++) {
        if (koppen[i].getBoundingClientRect().top < innerHeight * 0.35) akt = koppen[i]; else break;
      }
      var h1 = document.querySelector("h1");
      schrijf("leesplek", JSON.stringify({
        p: pagina, id: akt ? akt.id : "",
        h: akt ? akt.textContent.replace(/^#/, "").trim() : (h1 ? h1.textContent : ""), t: Date.now()
      }));
    }, 400);
  }
  addEventListener("scroll", opScroll, { passive: true });
  opScroll();
  if (boven) boven.addEventListener("click", function () { scrollTo({ top: 0, behavior: "smooth" }); });

  /* ---------- verder lezen ---------- */
  var q = new URLSearchParams(location.search).get("q");
  (function () {
    var vak = document.getElementById("verder");
    if (!vak || location.hash || q) return;
    var p; try { p = JSON.parse(lees("leesplek") || "null"); } catch (e) { p = null; }
    if (!p || !p.p || Date.now() - p.t > 60 * 864e5) return;
    var href = p.p + (p.id ? "#" + p.id : "");
    vak.innerHTML = '<span>Verder lezen:</span> <a href="' + esc(href) + '">' + esc(p.h) + ' →</a>' +
      '<button type="button" aria-label="Sluiten">✕</button>';
    vak.hidden = false;
    vak.querySelector("button").addEventListener("click", function () { vak.hidden = true; });
    vak.querySelector("a").addEventListener("click", function () { vak.hidden = true; });
    setTimeout(function () { vak.hidden = true; }, 15000);
  })();

  /* ---------- zoekterm markeren na een zoekopdracht ---------- */
  if (q && inhoud) {
    var norm = function (s) { return s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, ""); };
    var termen = [norm(q.trim())].concat(q.split(/\s+/).map(norm)).filter(function (w, i, a) { return w.length > 1 && a.indexOf(w) === i; });
    termen.sort(function (a, b) { return b.length - a.length; });
    var rx = new RegExp("(" + termen.map(function (w) { return w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }).join("|") + ")", "g");
    var walker = document.createTreeWalker(inhoud, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        return n.nodeValue.trim() && !n.parentElement.closest(".weergave, .vv, button, mark")
          ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      }
    });
    var nodes = [], n, teller = 0;
    while ((n = walker.nextNode())) nodes.push(n);
    nodes.forEach(function (node) {
      if (teller > 300) return;
      var t = node.nodeValue, nt = norm(t);
      if (nt.length !== t.length) return;
      rx.lastIndex = 0;
      if (!rx.test(nt)) return;
      var frag = document.createDocumentFragment(), last = 0, m;
      rx.lastIndex = 0;
      while ((m = rx.exec(nt))) {
        frag.appendChild(document.createTextNode(t.slice(last, m.index)));
        var mk = document.createElement("mark");
        mk.className = "zoekhit"; mk.textContent = t.slice(m.index, m.index + m[0].length);
        frag.appendChild(mk); last = m.index + m[0].length; teller++;
      }
      frag.appendChild(document.createTextNode(t.slice(last)));
      node.parentNode.replaceChild(frag, node);
    });
    var doel = location.hash ? document.getElementById(decodeURIComponent(location.hash.slice(1))) : null;
    var hits = Array.prototype.slice.call(inhoud.querySelectorAll("mark.zoekhit"));
    var na = hits.filter(function (h) {
      return !doel || (doel.compareDocumentPosition(h) & (Node.DOCUMENT_POSITION_FOLLOWING | Node.DOCUMENT_POSITION_CONTAINED_BY));
    });
    var vol = norm(q.trim());
    // liefst de volledige zoekterm, anders het eerste losse woord na het gekozen kopje
    var eerste = na.filter(function (h) { return norm(h.textContent) === vol; })[0] || na[0] || hits[0];
    if (eerste) {
      var det = eerste.closest("details"); if (det) det.open = true;
      eerste.classList.add("eerste");
      setTimeout(function () { eerste.scrollIntoView({ block: "center" }); }, 80);
    }
  }

  /* ---------- lightbox voor schermafbeeldingen ---------- */
  var lb = document.getElementById("lightbox");
  if (lb && inhoud) {
    var lbImg = lb.querySelector("img"), lbCap = lb.querySelector("figcaption"), lijst = [], pos = 0, vorigeFocus = null;
    var toon = function (i) {
      pos = (i + lijst.length) % lijst.length;
      lbImg.src = lijst[pos].getAttribute("href");
      var im = lijst[pos].querySelector("img");
      lbImg.alt = im ? im.alt : "";
      lbCap.textContent = (pos + 1) + " / " + lijst.length;
    };
    var sluit = function () { lb.hidden = true; document.body.style.overflow = ""; if (vorigeFocus) vorigeFocus.focus(); };
    inhoud.addEventListener("click", function (e) {
      var a = e.target.closest(".fig a.zoom");
      if (!a || e.ctrlKey || e.metaKey || e.shiftKey) return;
      e.preventDefault();
      lijst = Array.prototype.slice.call(inhoud.querySelectorAll(".fig a.zoom")).filter(function (x) { return x.offsetParent !== null; });
      vorigeFocus = a; lb.hidden = false; document.body.style.overflow = "hidden";
      toon(Math.max(0, lijst.indexOf(a))); lb.querySelector(".lb-sluit").focus();
    });
    lb.querySelector(".lb-sluit").addEventListener("click", sluit);
    lb.querySelector(".lb-vorige").addEventListener("click", function () { toon(pos - 1); });
    lb.querySelector(".lb-volgende").addEventListener("click", function () { toon(pos + 1); });
    lb.addEventListener("click", function (e) { if (e.target === lb || e.target.tagName === "FIGURE") sluit(); });
    document.addEventListener("keydown", function (e) {
      if (lb.hidden) return;
      if (e.key === "Escape") sluit();
      else if (e.key === "ArrowLeft") toon(pos - 1);
      else if (e.key === "ArrowRight") toon(pos + 1);
    });
    var x0 = null;
    lb.addEventListener("touchstart", function (e) { x0 = e.touches[0].clientX; }, { passive: true });
    lb.addEventListener("touchend", function (e) {
      if (x0 === null) return;
      var dx = e.changedTouches[0].clientX - x0; x0 = null;
      if (Math.abs(dx) > 50) toon(pos + (dx < 0 ? 1 : -1));
    });
  }
})();

/* ---------- spiekbrief: alleen ★ en alle antwoorden ---------- */
(function () {
  var ster = document.getElementById("sb-alleen-ster"), antw = document.getElementById("sb-antwoorden");
  if (ster) ster.addEventListener("click", function () {
    var aan = !document.body.classList.contains("sb-ster");
    document.body.classList.toggle("sb-ster", aan);
    ster.setAttribute("aria-pressed", aan ? "true" : "false");
  });
  if (antw) antw.addEventListener("click", function () {
    var ds = document.querySelectorAll(".sb-vragen details"), open = !Array.prototype.every.call(ds, function (d) { return d.open; });
    ds.forEach(function (d) { d.open = open; });
    antw.textContent = open ? "Antwoorden verbergen" : "Alle antwoorden tonen";
  });
})();
