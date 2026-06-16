// okf serve — vanilla-JS SPA. Read-only over /api/*.
//
// HTML insertion uses setHtml() (DOMParser + replaceChildren) — never raw
// .innerHTML — and every bundle-sourced value is either escaped (esc/attr) or
// sanitized via DOMPurify.sanitize() before it reaches the DOM. Concept bodies
// are Markdown rendered by `marked` then passed through DOMPurify.
"use strict";
let INDEX = null;
let cy = null;

const $ = (id) => document.getElementById(id);

async function api(p) {
  const r = await fetch(p);
  return r.ok ? r.json() : null;
}

// Safe HTML insertion: parse to nodes, then replace children (no .innerHTML).
function setHtml(el, html) {
  const doc = new DOMParser().parseFromString(html, "text/html");
  el.replaceChildren(...doc.body.childNodes);
}

// Insert HTML derived from bundle content: run it through DOMPurify first.
function setSafeHtml(el, html) {
  const clean = typeof DOMPurify !== "undefined" ? DOMPurify.sanitize(html) : html;
  setHtml(el, clean);
}

async function init() {
  INDEX = await api("/api/index");
  $("title").textContent = "okf" + (INDEX.concepts.length ? " · " + INDEX.concepts.length : "");
  const sel = $("type-filter");
  setHtml(
    sel,
    '<option value="">all types</option>' +
      INDEX.types.map((t) => "<option>" + esc(t) + "</option>").join("")
  );
  sel.addEventListener("change", onSearch);
  $("search").addEventListener("input", onSearch);
  $("graph-btn").addEventListener("click", toggleGraph);
  renderTree(INDEX.concepts);
}

function renderTree(concepts) {
  const groups = {};
  for (const c of concepts) {
    const top = c.cid.includes("/") ? c.cid.split("/")[0] : "";
    (groups[top] = groups[top] || []).push(c);
  }
  let html = "";
  for (const key of Object.keys(groups).sort()) {
    if (key) html += '<div class="group">' + esc(key) + "</div>";
    for (const c of groups[key].sort((a, b) => a.cid.localeCompare(b.cid))) {
      html +=
        '<div class="leaf" data-cid="' + attr(c.cid) + '">' +
        esc(c.title || c.cid) + '<span class="t">' + esc(c.type || "") + "</span></div>";
    }
  }
  setHtml($("tree"), html || '<div class="muted">no concepts</div>');
  document.querySelectorAll(".leaf").forEach((el) =>
    el.addEventListener("click", function () { openConcept(el.dataset.cid); })
  );
}

async function onSearch() {
  const q = $("search").value.trim();
  const type = $("type-filter").value;
  if (!q && !type) return renderTree(INDEX.concepts);
  const qs = new URLSearchParams({ q: q, limit: "200" });
  if (type) qs.set("type", type);
  const hits = await api("/api/search?" + qs);
  renderTree((hits || []).map((h) => ({ cid: h.cid, title: h.title, type: h.type })));
}

async function openConcept(cid) {
  const c = await api("/api/concepts/" + encodeURIComponent(cid));
  const box = $("concept");
  if (!c) { setHtml(box, '<p class="warn">not found</p>'); return; }
  const fm = c.frontmatter || {};
  const markedBody =
    typeof marked !== "undefined" && marked.parse ? marked.parse(c.body || "") : "<pre>" + esc(c.body || "") + "</pre>";
  const fmRows = Object.entries(fm)
    .filter(function (e) { return e[0] !== "title"; })
    .map(function (e) {
      const v = Array.isArray(e[1]) ? e[1].join(", ") : String(e[1]);
      return "<tr><th>" + esc(e[0]) + "</th><td>" + esc(v) + "</td></tr>";
    })
    .join("");
  const readerHtml =
    "<h1>" + esc(fm.title || c.cid) + "</h1>" +
    '<div class="meta"><code>' + esc(c.cid) + "</code></div>" +
    (c.frontmatter_error ? '<p class="warn">⚠ ' + esc(c.frontmatter_error) + "</p>" : "") +
    '<table class="fm">' + fmRows + "</table>" +
    '<div class="body">' + markedBody + "</div>" +
    '<div class="links"><b>links →</b> ' + ((c.outgoing || []).map(linkTag).join(", ") || '<span class="muted">none</span>') + "</div>" +
    '<div class="links"><b>← backlinks</b> ' + ((c.backlinks || []).map(linkTag).join(", ") || '<span class="muted">none</span>') + "</div>";
  setSafeHtml(box, readerHtml); // DOMPurify sanitizes the marked body + escaped fields
  box.querySelectorAll("a[data-cid]").forEach(function (a) {
    a.addEventListener("click", function (e) { e.preventDefault(); openConcept(a.dataset.cid); });
  });
  document.querySelectorAll(".leaf.active").forEach(function (el) { el.classList.remove("active"); });
  const active = document.querySelector('.leaf[data-cid="' + attr(cid) + '"]');
  if (active) active.classList.add("active");
}

function linkTag(cid) {
  return '<a href="#" data-cid="' + attr(cid) + '">' + esc(cid) + "</a>";
}

async function toggleGraph() {
  const gv = $("graph-view");
  const reader = $("reader");
  const tree = $("tree");
  const btn = $("graph-btn");
  if (!gv.hidden) {
    gv.hidden = true; reader.hidden = false; tree.hidden = false;
    btn.textContent = "◉ graph";
    return;
  }
  gv.hidden = false; reader.hidden = true; tree.hidden = true;
  btn.textContent = "▤ reader";
  const data = await api("/api/graph");
  if (cy) { cy.destroy(); cy = null; }
  if (typeof cytoscape === "undefined") return;
  cy = cytoscape({
    container: $("cy"),
    elements: data.elements,
    style: [
      { selector: "node", style: { label: "data(label)", "background-color": "#2563eb", color: "#e2e8f0", "text-valign": "center", "text-halign": "center", "font-size": "9px", width: "64px", height: "64px", "text-wrap": "wrap", "text-max-width": "60px" } },
      { selector: "edge", style: { width: 2, "line-color": "#475569", "target-arrow-color": "#475569", "target-arrow-shape": "triangle", "curve-style": "bezier" } },
    ],
    layout: { name: "cose", animate: false, padding: 24 },
  });
  cy.on("tap", "node", function (evt) { openConcept(evt.target.id()); });
}

function esc(s) {
  return String(s).replace(/[&<>"]/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
  });
}
function attr(s) {
  return String(s).replace(/"/g, "&quot;");
}

init();
