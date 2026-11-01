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

  /* ---------- episode page: player ---------- */
  var p = document.querySelector(".player");
  if (!p) return;
  var audio = p.querySelector("audio"), stat = p.querySelector(".pstat"), speed = p.querySelector(".speed"),
      embed = p.querySelector(".embed"), key = "cc-pos-" + p.getAttribute("data-id");

  function showEmbed(msg) {
    audio.hidden = true; speed.hidden = true;
    var id = p.getAttribute("data-spotify");
    stat.textContent = msg || "";
    if (id && embed.hidden) {
      var f = document.createElement("iframe");
      f.src = "https://open.spotify.com/embed/show/" + encodeURIComponent(id) + "?utm_source=generator";
      f.title = "Courtroom Chronicles on Spotify"; f.loading = "lazy";
      f.allow = "autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture";
      embed.appendChild(f); embed.hidden = false;
    }
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
