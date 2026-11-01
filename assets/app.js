/* Courtroom Chronicles: search/filter on the index, audio player on episode pages. No dependencies. */
(function () {
  "use strict";
  function norm(s) { return (s || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim(); }
  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) {} return null; }

  /* ---------- index: search, topic filter, sort ---------- */
  var list = document.getElementById("list");
  if (list) {
    var q = document.getElementById("q"), sort = document.getElementById("sort"), cnt = document.getElementById("count"),
        none = document.getElementById("none"), chips = document.querySelectorAll("#topics .chip"),
        cards = Array.prototype.slice.call(list.children), topic = "";
    var params = new URLSearchParams(location.search);
    if (params.get("q")) q.value = params.get("q");
    if (params.get("topic")) { topic = params.get("topic").toLowerCase(); }
    function apply() {
      var terms = norm(q.value).split(" ").filter(Boolean), shown = 0;
      cards.forEach(function (c) {
        var s = c.getAttribute("data-s"), ok = terms.every(function (t) { return s.indexOf(t) > -1; });
        if (ok && topic) ok = c.getAttribute("data-t").indexOf("|" + topic + "|") > -1;
        c.hidden = !ok; if (ok) shown++;
      });
      cards.sort(function (a, b) { var d = a.getAttribute("data-n") - b.getAttribute("data-n"); return sort.value === "old" ? d : -d; })
           .forEach(function (c) { list.appendChild(c); });
      cnt.textContent = shown + (shown === 1 ? " episode" : " episodes");
      none.hidden = shown !== 0;
      chips.forEach(function (b) { b.classList.toggle("on", b.getAttribute("data-t") === topic); });
    }
    q.addEventListener("input", apply); sort.addEventListener("change", apply);
    chips.forEach(function (b) { b.addEventListener("click", function () { topic = b.getAttribute("data-t"); apply(); }); });
    apply();
  }

  /* ---------- law finder filter ---------- */
  var lq = document.getElementById("lq");
  if (lq) {
    var rows = document.querySelectorAll(".lawlist li");
    lq.addEventListener("input", function () {
      var terms = norm(lq.value).split(" ").filter(Boolean);
      rows.forEach(function (r) { var s = r.getAttribute("data-s"); r.hidden = !terms.every(function (t) { return s.indexOf(t) > -1; }); });
      document.querySelectorAll(".lawgroup").forEach(function (g) { g.hidden = !g.querySelector("li:not([hidden])"); });
    });
  }

  /* ---------- share / copy ---------- */
  var cp = document.querySelector("[data-copy]");
  if (cp) cp.addEventListener("click", function () {
    var u = cp.getAttribute("data-copy");
    (navigator.clipboard ? navigator.clipboard.writeText(u) : Promise.reject()).then(function () { cp.textContent = "Link copied"; }, function () { window.prompt("Copy this link", u); });
  });
  var sh = document.querySelector("[data-share]");
  if (sh && navigator.share) {
    sh.hidden = false;
    sh.addEventListener("click", function () { navigator.share({ title: sh.getAttribute("data-share"), url: sh.getAttribute("data-url") }).catch(function () {}); });
  }

  /* ---------- episode page: player ---------- */
  var p = document.querySelector(".player");
  if (!p) return;
  var audio = p.querySelector("audio"), stat = p.querySelector(".pstat"), speed = p.querySelector(".speed"),
      embed = p.querySelector(".embed"), key = "cc-pos-" + p.getAttribute("data-id");

  function frame(kind) {
    var f = document.createElement("iframe");
    f.loading = "lazy";
    if (kind === "apple") {
      f.src = p.getAttribute("data-apple"); f.title = "Courtroom Chronicles on Apple Podcasts"; f.style.minHeight = "450px";
      f.allow = "autoplay *; encrypted-media *; fullscreen *; clipboard-write";
      f.setAttribute("sandbox", "allow-forms allow-popups allow-same-origin allow-scripts allow-storage-access-by-user-activation allow-top-navigation-by-user-activation");
    } else {
      f.src = "https://open.spotify.com/embed/show/" + encodeURIComponent(p.getAttribute("data-spotify")) + "?utm_source=generator";
      f.title = "Courtroom Chronicles on Spotify";
      f.allow = "autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture";
    }
    return f;
  }

  function showEmbed(msg) {
    audio.hidden = true; speed.hidden = true;
    stat.textContent = msg || "";
    if (!embed.hidden) return;
    var sp = p.getAttribute("data-spotify"), ap = p.getAttribute("data-apple");
    if (!sp && !ap) return;
    var holder = document.createElement("div"), cur = null;
    function pick(kind, btn) {
      if (cur === kind) return; cur = kind;
      holder.innerHTML = ""; holder.appendChild(frame(kind));
      if (btn) Array.prototype.forEach.call(embed.querySelectorAll(".tabs button"), function (b) { b.setAttribute("aria-pressed", b === btn ? "true" : "false"); });
    }
    if (sp && ap) {
      var tabs = document.createElement("div"); tabs.className = "tabs";
      [["spotify", "Spotify"], ["apple", "Apple Podcasts"]].forEach(function (k) {
        var b = document.createElement("button"); b.type = "button"; b.className = "btn ghost"; b.textContent = k[1];
        b.setAttribute("aria-pressed", k[0] === "spotify" ? "true" : "false");
        b.addEventListener("click", function () { pick(k[0], b); }); tabs.appendChild(b);
      });
      embed.appendChild(tabs);
    }
    embed.appendChild(holder); embed.hidden = false;
    pick(sp ? "spotify" : "apple");
  }

  function ready() {
    audio.hidden = false;
    var rates = [1, 1.25, 1.5, 1.75, 2, 0.85], i = 0;
    speed.hidden = false;
    speed.addEventListener("click", function () { i = (i + 1) % rates.length; audio.playbackRate = rates[i]; speed.textContent = rates[i] + "×"; });
    var saved = parseFloat(store(key));
    audio.addEventListener("loadedmetadata", function () { if (saved > 5 && saved < audio.duration - 10) { audio.currentTime = saved; stat.textContent = "Resumed where you left off."; } });
    var last = 0;
    audio.addEventListener("timeupdate", function () { var now = Date.now(); if (now - last > 4000) { last = now; store(key, String(audio.currentTime)); } });
    audio.addEventListener("ended", function () { store(key, null); });
    audio.addEventListener("error", function () { showEmbed("This audio file could not be loaded here. Play it on Spotify below."); });
  }

  if (audio.getAttribute("src")) { ready(); return; }

  /* No audio URL baked into the page: try the RSS feed directly, else fall back to the Spotify player. */
  var rss = p.getAttribute("data-rss"), title = p.getAttribute("data-title"), num = parseInt(p.getAttribute("data-num"), 10);
  if (!rss || !window.fetch) { showEmbed("Play this episode on Spotify below."); return; }
  stat.textContent = "Loading audio…";
  fetch(rss, { mode: "cors" }).then(function (r) { if (!r.ok) throw new Error("feed"); return r.text(); }).then(function (txt) {
    var doc = new DOMParser().parseFromString(txt, "text/xml"), items = Array.prototype.slice.call(doc.querySelectorAll("item")), hit = null;
    var re = new RegExp("\\b(ep|episode)\\s*0*" + num + "\\b");
    items.forEach(function (it) {
      if (hit) return;
      var t = norm((it.querySelector("title") || {}).textContent);
      if (t && title && (t.indexOf(title) > -1 || (title.indexOf(t) > -1 && t.length > 12))) hit = it;
    });
    if (!hit) items.forEach(function (it) { if (hit) return; if (re.test(norm((it.querySelector("title") || {}).textContent))) hit = it; });
    var enc = hit && hit.querySelector("enclosure");
    if (!enc || !enc.getAttribute("url")) throw new Error("nomatch");
    audio.src = enc.getAttribute("url"); stat.textContent = ""; ready();
  }).catch(function () { showEmbed("Play this episode on Spotify below."); });
})();
