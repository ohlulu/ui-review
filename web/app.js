"use strict";
// Fixed shell: renders /api/runs and /runs/<id>/manifest.json. Agents never write HTML.
const SCHEMA = 2;
const VERDICTS = [
  { v: "✅", icon: "check", label: "通過" },
  { v: "❌", icon: "x", label: "要改" },
  { v: "❓", icon: "question", label: "有疑問" },
];
// null: no tag. Every card of a screens run is a SCREEN, so a tag would say nothing.
const STATUS = {
  "CHANGED": ["Changed", "changed"],
  "NEW": ["New", "new"],
  "UNCHANGED": ["Unchanged", ""],
  "MOTION": ["Motion", "motion"],
  "SCREEN": null,
  "MISSING AFTER": ["Missing after", "bad"],
};
// Phosphor Icons (bold), MIT.
const ICONS = {
  back: "M168.49,199.51a12,12,0,0,1-17,17l-80-80a12,12,0,0,1,0-17l80-80a12,12,0,0,1,17,17L97,128Z",
  right: "M184.49,136.49l-80,80a12,12,0,0,1-17-17L159,128,87.51,56.49a12,12,0,1,1,17-17l80,80A12,12,0,0,1,184.49,136.49Z",
  down: "M216.49,104.49l-80,80a12,12,0,0,1-17,0l-80-80a12,12,0,0,1,17-17L128,159l71.51-71.52a12,12,0,0,1,17,17Z",
  check: "M232.49,80.49l-128,128a12,12,0,0,1-17,0l-56-56a12,12,0,1,1,17-17L96,183,215.51,63.51a12,12,0,0,1,17,17Z",
  x: "M208.49,191.51a12,12,0,0,1-17,17L128,145,64.49,208.49a12,12,0,0,1-17-17L111,128,47.51,64.49a12,12,0,0,1,17-17L128,111l63.51-63.52a12,12,0,0,1,17,17L145,128Z",
  question: "M196,96c0,29.47-24.21,54.05-56,59.06V156a12,12,0,0,1-24,0V144a12,12,0,0,1,12-12c24.26,0,44-16.15,44-36s-19.74-36-44-36S84,76.15,84,96a12,12,0,0,1-24,0c0-33.08,30.5-60,68-60S196,62.92,196,96Zm-68,92a20,20,0,1,0,20,20A20,20,0,0,0,128,188Z",
  done: "M176.49,95.51a12,12,0,0,1,0,17l-56,56a12,12,0,0,1-17,0l-24-24a12,12,0,1,1,17-17L112,143l47.51-47.52A12,12,0,0,1,176.49,95.51ZM236,128A108,108,0,1,1,128,20,108.12,108.12,0,0,1,236,128Zm-24,0a84,84,0,1,0-84,84A84.09,84.09,0,0,0,212,128Z",
  warn: "M240.26,186.1,152.81,34.23h0a28.74,28.74,0,0,0-49.62,0L15.74,186.1a27.45,27.45,0,0,0,0,27.71A28.31,28.31,0,0,0,40.55,228h174.9a28.31,28.31,0,0,0,24.79-14.19A27.45,27.45,0,0,0,240.26,186.1Zm-20.8,15.7a4.46,4.46,0,0,1-4,2.2H40.55a4.46,4.46,0,0,1-4-2.2,3.56,3.56,0,0,1,0-3.73L124,46.2a4.77,4.77,0,0,1,8,0l87.44,151.87A3.56,3.56,0,0,1,219.46,201.8ZM116,136V104a12,12,0,0,1,24,0v32a12,12,0,0,1-24,0Zm28,40a16,16,0,1,1-16-16A16,16,0,0,1,144,176Z",
};
const app = document.getElementById("app");

// Drops the false / null / 0 / "" left by `cond && node` so callers can inline optional parts.
function kids(list) {
  return list.flat(Infinity).filter(c => c != null && c !== false && c !== 0 && c !== "");
}

// The first render after page load gets the hero appear; later route changes render instantly.
let booted = false;

function show(...nodes) {
  app.replaceChildren(...kids(nodes));
  if (booted) return;
  booted = true;
  [...app.children].forEach((el, i) => el.style.setProperty("--i", Math.min(i, 10)));
  app.classList.add("intro");
  setTimeout(() => app.classList.remove("intro"), 1600);
}

function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids(children)) el.append(c instanceof Node ? c : String(c));
  return el;
}

function icon(name, cls) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 256 256");
  svg.setAttribute("class", `icon${cls ? ` ${cls}` : ""}`);
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS(ns, "path");
  path.setAttribute("d", ICONS[name]);
  svg.append(path);
  return svg;
}

function ago(seconds) {
  const d = Date.now() / 1000 - seconds;
  if (d < 60) return "剛剛";
  if (d < 3600) return `${Math.floor(d / 60)} 分鐘前`;
  if (d < 86400) return `${Math.floor(d / 3600)} 小時前`;
  return `${Math.floor(d / 86400)} 天前`;
}

function stamp(seconds) {
  return new Date(seconds * 1000).toLocaleString("zh-TW", { hour12: false });
}

async function getJSON(url) {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`${url} → ${res.status}`);
  return res.json();
}

async function postVerdict(run, body) {
  const res = await fetch(`/api/runs/${run}/verdict`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-UIReview": "1" },
    body: JSON.stringify(body),
  });
  return { status: res.status, data: await res.json().catch(() => ({})) };
}

// Run ids are lowercase on disk and in URLs; people read and say them as R12, like card ids C01.
function label(runId) {
  return runId.toUpperCase();
}

function tag(text, cls) {
  return h("span", { class: `tag caption-3${cls ? ` ${cls}` : ""}` }, text);
}

function notice(text, kind) {
  return h("div", { class: `notice body-6${kind ? ` ${kind}` : ""}` }, kind !== "info" && icon("warn"), h("span", {}, text));
}

function seg(labels, active, onpick) {
  const buttons = labels.map((label, i) => h("button", {
    type: "button",
    class: `button-sm${i === active ? " on" : ""}`,
    "aria-pressed": String(i === active),
    onclick: () => { select(i); onpick(i); },
  }, label));
  function select(i) {
    buttons.forEach((b, j) => { b.classList.toggle("on", i === j); b.setAttribute("aria-pressed", String(i === j)); });
  }
  const el = h("div", { class: "seg", role: "group" }, buttons);
  el.select = select;
  return el;
}

// ---------- list ----------

let projectFilter = null;
// A close from the list that failed survives the refresh that follows it.
let listNotice = null;

// Reads the newest rev first, so a close never sends a stale one; returns the HTTP status (0 when offline).
async function closeRun(runId) {
  try {
    const verdict = await getJSON(`/api/runs/${runId}/verdict`);
    return (await postVerdict(runId, { rev: verdict.rev, closed: true })).status;
  } catch {
    return 0;
  }
}

async function renderList(isCurrent) {
  const runs = await getJSON("/api/runs");
  if (!isCurrent()) return;
  document.title = "UI Review";
  const projects = [...new Set(runs.filter(r => r.project).map(r => r.project))];
  if (projectFilter && !projects.includes(projectFilter)) projectFilter = null;
  const shown = runs.filter(r => !projectFilter || r.project === projectFilter);
  const pending = shown.filter(r => !r.unsupported && !r.decided);
  const decided = shown.filter(r => !r.unsupported && r.decided);
  const unsupported = shown.filter(r => r.unsupported);
  const showProject = projects.length > 1 && !projectFilter;
  app.classList.remove("wide");

  const filters = projects.length > 1 && h("nav", { class: "filters", "aria-label": "Project" },
    [null, ...projects].map(p => h("button", {
      type: "button",
      class: `button-sm${projectFilter === p ? " on" : ""}`,
      "aria-pressed": String(projectFilter === p),
      onclick: () => { projectFilter = p; route(); },
    }, p || "全部")));

  const closeAll = pending.length > 1 && h("button", {
    type: "button",
    class: "closebtn close-all button-sm",
    onclick: async ev => {
      const scope = projectFilter ? ` ${projectFilter} 的` : "";
      if (!confirm(`關閉${scope}全部 ${pending.length} 個待裁決 run？會視為已裁決，7 天後清除。`)) return;
      ev.target.disabled = true;
      ev.target.textContent = "關閉中…";
      const results = await Promise.all(pending.map(r => closeRun(r.id)));
      const failed = pending.filter((_, i) => results[i] !== 200).map(r => label(r.id));
      if (failed.length) listNotice = `${failed.join("、")} 沒關成功，請再試一次`;
      route();
    },
  }, "全部關閉");
  const notices = listNotice && h("div", { class: "notices" }, notice(listNotice));
  listNotice = null;

  show(
    h("header", { class: "page-head" }, h("h1", { class: "heading-4 hero" }, "UI Review")),
    filters,
    notices,
    h("section", { class: "group" },
      h("div", { class: "group-head" },
        h("h2", { class: "group-label title-4" }, "待裁決", pending.length && h("span", { class: "count" }, pending.length)),
        closeAll),
      h("div", { class: "list" }, pending.length ? pending.map(r => pendingRow(r, showProject)) : h("div", { class: "empty" },
        icon("done"),
        h("div", { class: "title-3" }, "都看完了"),
        h("div", { class: "body-6 mute" }, "Agent 發佈新的 run 會出現在這裡")))),
    decided.length && h("section", { class: "group decided" },
      h("h2", { class: "group-label title-4" }, "已裁決"),
      h("div", { class: "list" }, decided.map(r => decidedRow(r, showProject)))),
    unsupported.length && h("section", { class: "group decided" },
      h("h2", { class: "group-label title-4" }, "不支援"),
      h("div", { class: "list" }, unsupported.map(r => h("div", { class: "row" }, h("div", { class: "main" },
        h("div", { class: "title title-3" }, label(r.id)),
        h("div", { class: "meta caption-5" }, `manifest schema ${r.unsupported}，這版網頁不支援`)))))),
  );
}

function pendingRow(r, showProject) {
  const meta = [showProject && r.project, r.round_of && `重做 ${label(r.round_of)}`, ago(r.published)].filter(Boolean).join(" · ");
  const close = h("button", {
    type: "button",
    class: "closebtn row-close",
    "aria-label": `關閉 ${label(r.id)}`,
    title: "關閉",
    onclick: async ev => {
      ev.preventDefault();
      ev.stopPropagation();
      if (!confirm(`關閉 ${label(r.id)}？會視為已裁決，7 天後清除。`)) return;
      const status = await closeRun(r.id);
      if (status !== 200) { listNotice = `${label(r.id)} 沒關成功（${status || "離線"}），請再試一次`; }
      route();
    },
  }, icon("x"));
  return h("a", { class: "row", href: `#${r.id}` },
    h("span", { class: "rid title-3" }, label(r.id)),
    h("div", { class: "main" },
      h("div", { class: "title title-3" }, r.title),
      h("div", { class: "meta caption-5" }, meta)),
    r.stale && tag("Stale", "warn"),
    close,
    r.need && h("span", { class: "need caption-3" }, `${r.remaining} 待看`),
    icon("right", "chev"));
}

function decidedRow(r, showProject) {
  const bad = r.counts["❌"];
  const [why, cls] = r.superseded_by ? [`被 ${label(r.superseded_by)} 取代`, ""] : r.closed ? ["已關閉", ""] : !r.need ? ["無變更", ""]
    : bad ? [`${bad} 張要改`, "bad"] : ["全部通過", "ok"];
  const meta = [showProject && r.project, r.decided_at && `${ago(r.decided_at)}裁決`].filter(Boolean).join(" · ");
  return h("a", { class: "row", href: `#${r.id}` },
    h("span", { class: "rid title-3" }, label(r.id)),
    h("div", { class: "main" },
      h("div", { class: "title title-3" }, r.title),
      meta && h("div", { class: "meta caption-5" }, meta)),
    h("span", { class: `outcome caption-4${cls ? ` ${cls}` : ""}` }, why),
    icon("right", "chev"));
}

// ---------- run ----------

// A close / reopen refused with 409 reloads the run; this carries the explanation into the fresh render.
let conflictNotice = null;

// Verdict sync, one state object per opened run: one request in flight, edits made meanwhile are queued per card
// and sent with the newest rev. Leaving the run leaves its object to finish saving on its own.

function newSync(run, verdict) {
  return { run, verdict, pending: {}, inflight: false, timers: {}, ui: {}, onchange: null };
}

function queue(s, card, value, delay) {
  s.pending[card] = value;
  clearTimeout(s.timers[card]);
  setStatus(s, card, "儲存中…");
  s.timers[card] = setTimeout(() => flush(s), delay);
  if (s.onchange) s.onchange();
}

async function flush(s) {
  if (s.inflight || !Object.keys(s.pending).length) return;
  const cards = s.pending;
  s.pending = {};
  s.inflight = true;
  let res;
  try {
    res = await postVerdict(s.run, { rev: s.verdict.rev, cards });
  } catch (err) {
    res = { status: 0, data: { error: String(err) } };
  }
  s.inflight = false;
  if (res.status === 200) {
    s.verdict = res.data;
    for (const c of Object.keys(cards)) if (!(c in s.pending)) setStatus(s, c, "已儲存");
  } else if (res.status === 409) {
    s.verdict = res.data;
    s.pending = {};
    for (const c of Object.keys(s.ui)) paintVerdict(s, c);
    for (const c of Object.keys(cards)) setStatus(s, c, "其他裝置剛改過，已載入最新狀態；請再按一次", true);
    return;
  } else {
    s.pending = { ...cards, ...s.pending };
    for (const c of Object.keys(cards)) setStatus(s, c, `沒存到（${res.status || "離線"}）：${res.data.error || ""}`, true);
    return;
  }
  flush(s);
}

function setStatus(s, card, text, error) {
  const el = s.ui[card] && s.ui[card].status;
  if (!el) return;
  el.textContent = text;
  el.classList.toggle("err", !!error);
}

function paintVerdict(s, card) {
  const ui = s.ui[card];
  const mark = s.verdict.cards[card] || {};
  pressVerdict(ui.buttons, mark.v);
  if (document.activeElement !== ui.note) ui.note.value = mark.note || "";
  if (s.onchange) s.onchange();
}

function pressVerdict(buttons, v) {
  buttons.forEach(b => {
    b.classList.toggle("on", b.dataset.v === v);
    b.setAttribute("aria-pressed", String(b.dataset.v === v));
  });
}

function current(s, card) {
  const ui = s.ui[card];
  const on = ui.buttons.find(b => b.classList.contains("on"));
  return { v: on ? on.dataset.v : null, note: ui.note.value };
}

async function renderRun(runId, cardId, isCurrent) {
  const [manifest, verdict] = await Promise.all([
    getJSON(`/runs/${runId}/manifest.json`),
    getJSON(`/api/runs/${runId}/verdict`),
  ]);
  if (!isCurrent()) return;
  const back = h("a", { class: "back title-4", href: "#" }, icon("back"), "全部");
  if (manifest.schema !== SCHEMA) {
    show(back, h("h1", { class: "heading-5" }, label(runId)), notice(`manifest schema ${manifest.schema} 不支援（這版網頁只認 ${SCHEMA}）`));
    return;
  }
  const s = newSync(runId, verdict);
  document.title = `${label(runId)} · ${manifest.title}`;
  app.classList.add("wide");

  const notices = [
    conflictNotice && notice(conflictNotice),
    verdict.superseded_by && notice(`已被 ${label(verdict.superseded_by)} 取代`, "info"),
    verdict.closed && notice("這個 run 已關閉", "info"),
    manifest.round_of && notice(`這是 ${label(manifest.round_of)} 的重做`, "info"),
    manifest.identical_builds && notice("Before 和 After 是同一個 build（A/A），應該每張都沒變"),
  ].filter(Boolean);
  conflictNotice = null;
  const checks = manifest.checks || [];
  const status = h("div", { class: "saved caption-5" });

  // Marks only cards without a mark yet, so an ❌ or ❓ already given is never overwritten.
  const needIds = manifest.cards.filter(c => c.status !== "UNCHANGED").map(c => c.id);
  const unmarked = () => needIds.filter(id => !current(s, id).v);
  const passAll = h("button", {
    type: "button",
    class: "btn pass-all button-md",
    onclick: () => {
      for (const id of unmarked()) {
        pressVerdict(s.ui[id].buttons, "✅");
        queue(s, id, current(s, id), 0);
      }
    },
  });
  s.onchange = () => {
    const n = unmarked().length;
    passAll.hidden = !n;
    passAll.replaceChildren(icon("check"), n === needIds.length ? `全部通過 · ${n} 張` : `剩下 ${n} 張全部通過`);
  };

  show(
    back,
    h("header", { class: "run-head" },
      h("div", { class: "eyebrow caption-4" }, [manifest.project, `${ago(manifest.created)}拍攝`].filter(Boolean).join(" · ")),
      h("h1", { class: "heading-5" }, h("span", { class: "rid" }, label(runId)), " ", manifest.title)),
    notices.length && h("div", { class: "notices" }, notices),
    manifest.judge && h("div", { class: "judge" },
      h("div", { class: "label caption-3" }, "需要你判斷"),
      h("p", { class: "body-3" }, manifest.judge)),
    checks.length && h("details", { class: "checks body-6" },
      h("summary", { class: "caption-4" }, `Agent 回報的檢查 · ${checks.length}`, icon("down")),
      h("ul", {}, checks.map(c => h("li", {}, c)))),
    manifest.cards.map(c => renderCard(s, c, manifest.mode === "screens")),
    h("footer", { class: "run-foot" },
      passAll,
      h("button", {
        type: "button",
        class: "btn button-sm",
        onclick: async () => {
          const closing = !s.verdict.closed;
          if (closing && !confirm(`關閉 ${label(runId)}？未裁決的卡片也視為結案。`)) return;
          const res = await postVerdict(runId, { rev: s.verdict.rev, closed: closing });
          if (res.status === 200 && closing) { location.hash = ""; return; }
          if (res.status === 409) conflictNotice = `其他裝置剛改過，已載入最新狀態；${closing ? "關閉" : "重新開啟"}沒有生效，請再按一次`;
          if (res.status === 200 || res.status === 409) return route();
          status.textContent = `失敗（${res.status}）`;
          status.classList.add("err");
        },
      }, verdict.closed ? "重新開啟這個 run" : "關閉這個 run"),
      status,
      techDetails(manifest)),
  );
  for (const c of Object.keys(s.ui)) paintVerdict(s, c);
  s.onchange();
  if (cardId) {
    const el = document.getElementById(cardId);
    if (el) { setOpen(el, true); el.scrollIntoView(); }
  } else {
    window.scrollTo(0, 0);
  }
}

function renderCard(s, card, screens) {
  const src = file => `/runs/${s.run}/${file}`;
  const unchanged = card.status === "UNCHANGED";
  const status = card.status in STATUS ? STATUS[card.status] : [card.status, ""];
  const head = h("div", unchanged ? {
    class: "card-head",
    role: "button",
    tabindex: "0",
    "aria-expanded": "false",
    onclick: () => toggle(),
    onkeydown: ev => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); toggle(); } },
  } : { class: "card-head" },
    h("span", { class: "id caption-4" }, card.id),
    h("h2", { class: "title-3" }, card.label || card.name),
    status && tag(...status),
    unchanged && icon("down", "chev"));

  const buttons = VERDICTS.map(({ v, icon: name, label }) => h("button", {
    type: "button",
    class: "vbtn button-md",
    "data-v": v,
    "aria-pressed": "false",
    onclick: () => {
      const on = !buttons.find(b => b.dataset.v === v).classList.contains("on");
      pressVerdict(buttons, on ? v : null);
      queue(s, card.id, current(s, card.id), 0);
    },
  }, icon(name), label));
  const note = h("textarea", {
    class: "note", rows: "2", placeholder: "備註（可空白）", maxlength: "1000", "aria-label": `${card.id} 備註`,
    oninput: () => queue(s, card.id, current(s, card.id), 800),
  });
  const saved = h("div", { class: "saved caption-5", "aria-live": "polite" });
  s.ui[card.id] = { buttons, note, status: saved };

  const media = kids([
    compare(card, src, screens),
    card.video && video(card, src, screens),
    card.video_error && notice(`錄影失敗：${card.video_error}`),
    (card.rois || []).map(roi => roiPair(card, roi, src, screens)),
  ]);
  // Wide screens put media on the left and text + verdict on the right; narrow screens read top to bottom.
  const section = h("section", { class: `card${unchanged ? " unchanged" : ""}`, id: card.id },
    head,
    h("div", { class: `card-body${media.length ? " split" : ""}` },
      h("div", { class: "info" },
        card.what && h("p", { class: "what body-3" }, card.what),
        card.look && card.look.length && h("ul", { class: "look body-6" }, card.look.map(l => h("li", {}, l))),
        card.question && h("div", { class: "question body-6" }, h("div", { class: "label caption-3" }, "問題"), card.question),
        unchanged && h("p", { class: "what body-6 mute" }, "像素相同（容差 1%），切換看不到差異是正常的。"),
        card.stable === false && notice("連拍時畫面一直在變，差異可能是動畫殘留")),
      media.length && h("div", { class: "media" }, media),
      h("div", { class: "act" },
        h("div", { class: "verdict" }, buttons),
        note,
        saved)));

  function toggle() {
    setOpen(section, !section.classList.contains("open"));
  }
  return section;
}

// Every path that expands a card (tap, keyboard, deep link) goes through here so aria-expanded stays in sync.
function setOpen(section, open) {
  section.classList.toggle("open", open);
  const head = section.querySelector(".card-head[aria-expanded]");
  if (head) head.setAttribute("aria-expanded", String(open));
}

function shotImage(card, side, src, onready) {
  return h("img", {
    onload: ev => { ev.target.classList.add("ready"); onready(); },
    onerror: ev => { ev.target.replaceWith(h("p", { class: "caption-5 err" }, `${side} 圖片載入失敗`)); onready(); },
    src: src(card[side].img),
    alt: `${card.label || card.name} ${side}`,
    loading: "lazy",
    decoding: "async",
  });
}

// screens: a lone After is the whole point of the run, so it carries no "only After" tag.
function compare(card, src, screens) {
  const sides = ["before", "after"].filter(side => card[side]);
  if (!sides.length) return null;
  const size = card[sides[0]];
  const box = h("div", { class: "shot loading", style: size.w && size.h ? `aspect-ratio:${size.w}/${size.h};--ratio:${size.w / size.h}` : null });
  const done = () => box.classList.remove("loading");
  // Both sides stay stacked in the DOM so the swap never waits for a decode.
  const images = sides.map((side, i) => {
    const img = shotImage(card, side, src, done);
    if (i > 0) img.classList.add("off");
    return img;
  });
  box.append(...images);
  const title = `${card.id} · ${card.label || card.name}`;
  const zoomSides = sides.map(side => ({ label: side === "before" ? "Before" : "After", src: src(card[side].img) }));
  if (sides.length === 1) {
    const only = !screens && (sides[0] === "after" ? "只有 After" : "只有 Before");
    if (only) box.append(h("span", { class: "side-tag caption-3" }, only));
    zoomable(box, { title, sides: zoomSides, at: () => 0, pick: () => {}, note: only });
    return h("div", { class: "compare" }, box);
  }
  let showing = 0;
  const pick = i => { showing = i; images.forEach((img, j) => img.classList.toggle("off", i !== j)); };
  const control = seg(["Before", "After"], 0, pick);
  // The viewer's swap carries back here, so closing it leaves the inline shot on the side last looked at.
  zoomable(box, { title, sides: zoomSides, at: () => showing, pick: i => { pick(i); control.select(i); } });
  return h("div", { class: "compare" }, control, box);
}

function video(card, src, screens) {
  // iOS Safari paints nothing before the first tap unless the source names a start time.
  const el = h("video", { src: `${src(card.video.src)}#t=0.001`, playsinline: true, muted: true, loop: true, controls: true, preload: "metadata" });
  el.muted = true;
  const rates = [1, 0.5, 0.25];
  const speeds = seg(rates.map(r => `${r}×`), 0, i => { el.playbackRate = rates[i]; });
  const layout = card.video.sides.length === 2 ? "上 Before · 下 After"
    : !screens && `只有 ${card.video.sides[0] === "after" ? "After" : "Before"}`;
  return h("div", { class: "video" }, el, h("div", { class: "video-bar" }, speeds, layout && h("span", { class: "caption-5 mute" }, layout)));
}

function roiPair(card, roi, src, screens) {
  const width = roi.width_pt || 0;
  const present = ["before", "after"].filter(side => roi[side]);
  const zoomSides = present.map(side => ({ label: side === "before" ? "Before" : "After", src: src(roi[side]) }));
  const title = `${card.id} · ${roi.label}`;
  // Each crop asks for its 1:1 width; the pair wraps to a stack when both do not fit side by side.
  const fig = side => roi[side] && h("figure", { style: width ? `flex-basis:${width}px` : null },
    zoomable(
      h("img", { src: src(roi[side]), alt: `${roi.label} ${side}`, loading: "lazy", decoding: "async", style: width ? `max-width:${width}px` : null }),
      { title, sides: zoomSides, at: () => present.indexOf(side), pick: () => {} }),
    !screens && h("figcaption", { class: "caption-4" }, side === "before" ? "Before" : "After"));
  return h("div", { class: "roi" },
    h("div", { class: "roi-label" }, h("span", { class: "title-4" }, roi.label), h("span", { class: "scale caption-5" }, "1:1")),
    h("div", { class: "pair" }, fig("before"), fig("after")));
}

function techDetails(manifest) {
  const git = side => side.git && side.git.sha ? ` · ${side.git.sha}${side.git.dirty ? "+dirty" : ""}` : "";
  const rows = [
    manifest.base && ["Base", `${manifest.base.id} · ${manifest.base.hash}${git(manifest.base)}`],
    ["After", `${manifest.after.hash}${git(manifest.after)}`],
    ["拍攝", stamp(manifest.created)],
  ].filter(Boolean);
  return h("details", { class: "tech body-6" },
    h("summary", { class: "caption-4" }, "技術細節", icon("down")),
    h("table", {}, rows.map(([k, v]) => h("tr", {}, h("td", {}, k), h("td", {}, v)))));
}

// ---------- viewer ----------

// item: { title, sides: [{ label, src }], at() → side shown when opened, pick(i) → mirror a swap inline, note? }.
function zoomable(el, item) {
  el.zoom = item;
  el.classList.add("zoomable");
  el.setAttribute("role", "button");
  el.setAttribute("tabindex", "0");
  el.setAttribute("aria-label", `放大 ${item.title}`);
  el.addEventListener("click", () => openViewer(el));
  el.addEventListener("keydown", ev => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); openViewer(el); } });
  return el;
}

let viewer = null;

function openViewer(opener) {
  if (!viewer) viewer = buildViewer();
  // Collapsed unchanged cards have no layout box, so browsing skips them.
  const gallery = [...app.querySelectorAll(".zoomable")].filter(el => el.getClientRects().length);
  viewer.open(gallery, gallery.indexOf(opener));
}

function closeViewer() {
  if (viewer && viewer.dialog.open) viewer.dialog.close();
}

function buildViewer() {
  let gallery = [], index = 0, item = null, images = [], showing = 0;
  const count = h("span", { class: "viewer-count caption-4" });
  const title = h("span", { class: "viewer-title title-4" });
  const original = h("a", { class: "viewer-open button-sm", target: "_blank", rel: "noopener" }, "原圖");
  const frame = h("div", { class: "viewer-frame" });
  const control = seg(["Before", "After"], 0, i => pick(i));
  const note = h("span", { class: "viewer-note caption-4" });
  const prev = h("button", { type: "button", class: "icon-btn", "aria-label": "上一張", onclick: () => go(index - 1) }, icon("back"));
  const next = h("button", { type: "button", class: "icon-btn", "aria-label": "下一張", onclick: () => go(index + 1) }, icon("right"));
  const dialog = h("dialog", {
    class: "viewer",
    tabindex: "-1",
    "aria-label": "截圖",
    // A tap on the screenshot swaps sides like the inline switch; a tap anywhere around it closes.
    onclick: ev => {
      if (ev.target.tagName === "IMG") { if (images.length > 1) pick(1 - showing); }
      else if (ev.target === dialog || ev.target.classList.contains("viewer-stage") || ev.target === frame) dialog.close();
    },
    onkeydown: ev => {
      if (ev.key === "ArrowLeft") go(index - 1);
      else if (ev.key === "ArrowRight") go(index + 1);
    },
    onclose: () => {
      frame.replaceChildren();
      const el = gallery[index];
      if (el && el.isConnected) el.focus();
    },
  },
    h("div", { class: "viewer-bar" }, count, title, original,
      h("button", { type: "button", class: "icon-btn", "aria-label": "關閉", onclick: () => dialog.close() }, icon("x"))),
    h("div", { class: "viewer-stage" }, frame),
    h("div", { class: "viewer-foot" }, prev, h("div", { class: "viewer-mid" }, control, note), next));
  document.body.append(dialog);

  function go(i) {
    if (!gallery.length) return;
    index = (i + gallery.length) % gallery.length;
    item = gallery[index].zoom;
    showing = item.at();
    // Both sides stay stacked so the swap never waits for a decode, same as the inline shot.
    images = item.sides.map((side, j) => h("img", { src: side.src, alt: `${item.title} ${side.label}`, class: j === showing ? null : "off" }));
    frame.replaceChildren(...images);
    count.textContent = `${index + 1} / ${gallery.length}`;
    title.textContent = item.title;
    prev.hidden = next.hidden = gallery.length < 2;
    control.hidden = images.length < 2;
    control.select(showing);
    note.textContent = item.note || "";
    original.href = item.sides[showing].src;
  }

  function pick(i) {
    showing = i;
    images.forEach((img, j) => img.classList.toggle("off", i !== j));
    control.select(i);
    original.href = item.sides[i].src;
    item.pick(i);
  }

  return {
    dialog,
    open(list, at) {
      gallery = list;
      go(Math.max(at, 0));
      dialog.showModal();
      dialog.focus();
    },
  };
}

// ---------- routing ----------

// Each route bumps the generation, so a slow response for a page the user already left cannot repaint it.
let routeGen = 0;

async function route() {
  closeViewer();
  const gen = ++routeGen;
  const isCurrent = () => gen === routeGen;
  const [runId, cardId] = location.hash.replace(/^#\/?/, "").split("/");
  try {
    if (runId && /^r[0-9]+$/i.test(runId)) await renderRun(runId.toLowerCase(), cardId, isCurrent);
    else await renderList(isCurrent);
  } catch (err) {
    if (isCurrent()) show(h("a", { class: "back title-4", href: "#" }, icon("back"), "全部"), notice(`載入失敗：${err.message}`));
  }
}

let lastRun = null;
window.addEventListener("hashchange", () => {
  const runId = location.hash.replace(/^#\/?/, "").split("/")[0];
  const cardId = location.hash.split("/")[1];
  if (runId && runId === lastRun && cardId) {
    const el = document.getElementById(cardId);
    if (el) { closeViewer(); setOpen(el, true); el.scrollIntoView(); return; }
  }
  lastRun = runId || null;
  route();
});
window.addEventListener("pageshow", ev => { if (ev.persisted) route(); });
lastRun = location.hash.replace(/^#\/?/, "").split("/")[0] || null;
route();
