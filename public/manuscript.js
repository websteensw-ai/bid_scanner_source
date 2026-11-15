/* 원고지 배치·글자 수 (가이드 7장) — src/mvp/text.py 와 같은 규칙 */
(function () {
  var COLS = 20, ROWS = 20, MAX = 800, GUIDE = 700;
  var HANG = ".,?!:;'\")」』…·";
  function official(t) { return Array.from(t.replace(/\r/g, "").replace(/\n/g, "").normalize("NFC")).filter(function (c) { return !/\p{M}/u.test(c); }).length; }
  function disp(p) { return p.replace(/\s+/g, " ").trim().replace(/([.,]) /g, "$1"); }
  function tokens(p) { var o = [], i = 0, r = /[0-9a-z]/; var a = Array.from(p);
    while (i < a.length) { if (r.test(a[i]) && i + 1 < a.length && r.test(a[i + 1])) { o.push(a[i] + a[i + 1]); i += 2; } else { o.push(a[i]); i++; } } return o; }
  function layout(text) { var rows = [];
    text.replace(/\r/g, "").split("\n").forEach(function (raw) { var p = disp(raw); if (!p) return;
      var row = [""]; rows.push(row);
      tokens(p).forEach(function (t) {
        if (row.length === COLS) { if (HANG.indexOf(t) >= 0) { row[row.length - 1] += t; return; } row = []; rows.push(row); }
        if (t === " " && row.length === 0) return; row.push(t); }); });
    return rows.map(function (r) { while (r.length < COLS) r.push(""); return r; }); }
  function cells(text) { var r = layout(text); if (!r.length) return 0; var last = r[r.length - 1], n = 0;
    for (var i = 0; i < COLS; i++) if (last[i]) n = i + 1; return (r.length - 1) * COLS + n; }
  window.mvpLayout = layout;
  var ta = document.getElementById("body"); if (!ta) return;
  var grid = document.getElementById("grid"), composing = false, pastes = [], dirty = false;
  function draw() {
    if (composing) return;
    var t = ta.value, n = official(t), c = cells(t);
    var nc = document.getElementById("nChars"), ncl = document.getElementById("nCells");
    if (nc) { nc.textContent = n; nc.parentNode.classList.toggle("over", n > GUIDE); }
    if (ncl) ncl.textContent = c;
    if (!grid || grid.style.display === "none") return;
    var rows = layout(t), h = "";
    for (var s = 0; s < 2; s++) {
      h += '<div class="sheet"><div class="sheet-h">' + (s + 1) + '장 · 누적 ' + (s * 400 + 1) + '~' + ((s + 1) * 400) + '칸</div>';
      for (var r = 0; r < ROWS; r++) { var row = rows[s * ROWS + r] || [];
        h += '<div class="gr' + ((s === 1 && r === 14) ? ' guide' : '') + '">';
        for (var k = 0; k < COLS; k++) h += '<span>' + (row[k] ? row[k].replace(/&/g, "&amp;").replace(/</g, "&lt;") : "") + '</span>';
        h += '</div>'; }
      h += '</div>'; }
    grid.innerHTML = h + (rows.length > 40 ? '<div class="alert warn">원고지 800칸을 넘었어요.</div>' : "");
  }
  window.mvpView = function (v) { ta.style.display = v === "text" ? "" : "none"; grid.style.display = v === "grid" ? "" : "none"; draw(); };
  ta.addEventListener("compositionstart", function () { composing = true; });
  ta.addEventListener("compositionend", function () { composing = false; draw(); dirty = true; });
  ta.addEventListener("input", function () {
    if (!composing && cells(ta.value) > MAX) { alert("원고지 800칸을 넘을 수 없어요."); }
    dirty = true; draw(); });
  ta.addEventListener("paste", function (e) { var d = (e.clipboardData || window.clipboardData).getData("text"); if (d) pastes.push(official(d)); });
  function save() {
    if (ta.dataset.autosave === "off") return;
    if (!dirty || composing) return; dirty = false;
    var st = document.getElementById("saveState"); if (st) st.textContent = "저장 중…";
    fetch("/mvp/write/autosave", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: ta.value, pastes: pastes.splice(0) }) })
      .then(function (r) { return r.json(); })
      .then(function (j) { if (st) st.textContent = j.ok ? "저장됨 " + new Date().toLocaleTimeString() : (j.error || "저장 실패"); })
      .catch(function () { if (st) st.textContent = "저장 실패 · 다시 시도해요"; dirty = true; });
  }
  setInterval(save, 10000);
  window.addEventListener("beforeunload", save);
  if (grid) grid.style.display = "none";
  draw();
})();
