"use strict";

const TASKS = {
  py_cron: { name: "Cron parser module with tests", kind: "Python module",
    why: "3/4 successes each (Direct lost 1 to a 74-minute API stall; Tandem lost 1 to a 141 s slow test suite before TANDEM_SLOW_CHECK_S=30 was added)." },
  web_boids: { name: "Boids web simulation", kind: "Web page",
    why: "4/4 successes on both arms, both at 60 FPS; Tandem cuts cloud cost per success in half." },
  gen_orbital: { name: "Orbital web simulation", kind: "Web page",
    why: "Two Tandem artifacts passed the evaluator but ran over budget on orchestrator checks; final Tandem Orbital hit a GPU reset and fell back to Opus. Three Direct attempts missed an intermittent browser check." },
  gen_portal: { name: "3D neon portal (4 files)", kind: "3D web app",
    why: "2/4 successes on both arms. The 40 FPS gate lifted slow Tandem portals from 3–4 FPS to 60 FPS in confirm (38–39 vs 40 FPS in final), at 78% lower cloud cost per success." },
};
const ORDER = ["py_cron", "web_boids", "gen_orbital", "gen_portal"];
const RUN_TAG = (run) => {
  if (!run) return "";
  if (run.includes("pilot1")) return "pilot · ";
  if (run.includes("confirm")) return "confirm · ";
  if (run.includes("final")) return "final · ";
  return "";
};
const DEMOS = {
  orbital: { d: "orbital/direct", t: "orbital/tandem", cd: "pilot p1 · passed", ct: "confirm p2 · passed",
    note: "Both pass all three evaluations and run at 60 FPS. Direct adds extra visual polish (tapered trails and usage hint); Tandem finished in 11 min for $0.15 cloud." },
  portal: { d: "portal/direct", t: "portal/tandem", cd: "final p1 · failed (interactions)", ct: "final p1 · passed",
    note: "Same final 4.1.0 pair. Direct has neon wireframe edges and a full cross-grid (40 FPS at 1280x800) but fails interactions; Tandem passes all three evaluations (38–39 FPS at 1280x800) for $0.11 cloud." },
};
// pages render at a desktop size and are scaled down; a phone gets a smaller virtual size so the controls stay legible
const viewW = (stage) => (stage.clientWidth < 560 ? 760 : 1280);
let demo = "orbital", mode = "live";

const $ = (s) => document.querySelector(s);
const usd = (v) => v == null ? "n/a" : "$" + v.toFixed(v < 0.1 ? 4 : 3);
const pct = (v) => (v > 0 ? "+" : "") + Math.round(v * 100) + "%";
const k = (v) => v >= 10000 ? Math.round(v / 1000) + "k" : v.toLocaleString("en-US");
const dur = (s) => s < 90 ? Math.round(s) + " s" : s < 5400 ? Math.round(s / 60) + " min" : (s / 3600).toFixed(1) + " h";
const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };

function totals(data, arm) {
  const rows = data.attempts.filter((a) => a.arm === arm);
  const cost = rows.reduce((s, a) => s + a.cost_usd, 0);
  const ok = rows.filter((a) => a.success).length;
  const correct = rows.filter((a) => a.success || (a.timed_out && !a.failed_checks.length)).length;
  const out = ORDER.reduce((s, t) => s + data.summary[t][arm].tokens_total.output_tokens, 0);
  return { n: rows.length, cost, ok, correct, out, per: cost / ok };
}

function renderKpis(data) {
  const d = totals(data, "direct"), t = totals(data, "tandem");
  const cards = [
    [pct(t.per / d.per - 1), "Cloud cost per success", `${usd(t.per)} with Tandem, ${usd(d.per)} direct`],
    [pct(t.cost / d.cost - 1), "Total cloud spend", `$${t.cost.toFixed(2)} against $${d.cost.toFixed(2)}, ${d.n} attempts each`],
    [pct(t.out / d.out - 1), "Cloud output tokens", `${k(t.out)} against ${k(d.out)}`],
    [`${t.ok} vs ${d.ok}`, "Successes of " + d.n, `Ignoring budget: Tandem ${t.correct}, direct ${d.correct}`, true],
  ];
  const box = $("#kpis");
  for (const [big, lbl, det, neutral] of cards) {
    const c = el("div", "kpi");
    c.append(el("div", "big" + (neutral ? " neutral" : ""), big), el("div", "lbl", lbl), el("div", "det", det));
    box.append(c);
  }
  $("#note-punctual").innerHTML = `<b>Trade-off and caveats:</b> 4.1.0 cut local per-call time by ~40–45% and dropped median task time from 25 min to 19 min, but Tandem is still ~13x slower than direct (~7–39 min median vs ~1–2.5 min). Excluding two infrastructure incidents in the final run (a GPU reset on Tandem Orbital and a 74-minute API stall on Direct Cron): 10/15 successes each, $0.205 vs $0.521 (-61%, -72% output tokens). Small edits (&lt;30 lines) stay direct (+10% in 4.0.0).`;
}

function renderTasks(data) {
  const box = $("#task-cards");
  for (const id of ORDER) {
    const s = data.summary[id], info = TASKS[id];
    const metric = (a) => s[a].cost_usd_per_success ?? s[a].cost_usd_total / s[a].attempts;
    const max = Math.max(metric("direct"), metric("tandem"));
    const perAttempt = s.direct.cost_usd_per_success == null || s.tandem.cost_usd_per_success == null;
    const delta = perAttempt ? metric("tandem") / metric("direct") - 1 : s.tandem_vs_direct_per_success;
    const c = el("article", "task");
    const h = el("h3");
    h.append(el("span", "", info.name),
      el("span", "delta " + (delta < 0 ? "good" : "bad"), pct(delta) + (perAttempt ? "*" : "")));
    c.append(h, el("div", "budget", `${info.kind} · budget ${dur(data.budgets[id])}`));
    for (const arm of ["direct", "tandem"]) {
      const a = s[arm];
      const r = el("div", "row " + arm[0]);
      r.append(el("span", "who " + (arm === "direct" ? "arm-d" : "arm-t"), arm === "direct" ? "Direct" : "Tandem"));
      const bar = el("div", "bar"); const fill = el("i"); fill.style.width = (metric(arm) / max * 100).toFixed(1) + "%";
      bar.append(fill); r.append(bar);
      const cost = a.cost_usd_per_success == null ? `<b>${usd(metric(arm))}</b> per attempt` : `<b>${usd(a.cost_usd_per_success)}</b> per success`;
      r.append(el("div", "meta", `<span>${cost}</span><span>${a.successes}/${a.attempts} ok</span><span>median ${dur(a.median_wall_seconds)}</span>`));
      c.append(r);
    }
    c.append(el("p", "why", (perAttempt ? "* per attempt. " : "") + info.why));
    box.append(c);
  }
}

function renderTokens(data) {
  const sum = (arm, key) => ORDER.reduce((s, t) => s + data.summary[t][arm].tokens_total[key], 0);
  const rows = [["Output", "output_tokens"], ["Cache writes", "cache_creation_input_tokens"], ["Cache reads", "cache_read_input_tokens"]];
  let html = "<thead><tr><th>Cloud tokens</th><th class='arm-d'>Direct</th><th class='arm-t'>Tandem</th><th>Change</th></tr></thead><tbody>";
  for (const [lbl, key] of rows) {
    const d = sum("direct", key), t = sum("tandem", key);
    html += `<tr><td>${lbl}</td><td>${d.toLocaleString("en-US")}</td><td>${t.toLocaleString("en-US")}</td><td>${pct(t / d - 1)}</td></tr>`;
  }
  const loc = ORDER.reduce((s, t) => s + data.summary[t].tandem.local_tokens_total, 0);
  html += `<tr><td>Local model tokens (free)</td><td>0</td><td>${loc.toLocaleString("en-US")}</td><td></td></tr></tbody>`;
  $("#tokens").innerHTML = html;
}

function renderAttempts(data, filter) {
  const box = $("#attempt-list");
  box.textContent = "";
  for (const a of data.attempts.filter((x) => filter === "all" || x.task === filter)) {
    const st = a.success ? ["ok", "pass"] : a.timed_out && !a.failed_checks.length ? ["late", "correct, late"] : ["ko", "fail"];
    const c = el("div", "att " + a.arm);
    c.append(el("div", "top", `<span>${TASKS[a.task].name.split(" (")[0]} · ${RUN_TAG(a.run)}p${a.pair} · <span class="${a.arm === "direct" ? "arm-d" : "arm-t"}">${a.arm}</span></span><span class="st ${st[0]}">${st[1]}</span>`));
    let dl = `<dt>Cloud cost</dt><dd>${usd(a.cost_usd)}</dd><dt>Time</dt><dd>${dur(a.wall_seconds)}</dd><dt>Cloud output</dt><dd>${k(a.output_tokens)} tok</dd>`;
    if (a.arm === "tandem") dl += `<dt>Local tokens</dt><dd>${k(a.local_tokens)}</dd>`;
    if (a.failed_checks.length) dl += `<dt>Failed</dt><dd>${a.failed_checks.join(", ")}</dd>`;
    c.append(el("dl", "", dl));
    box.append(c);
  }
}

function renderFilters(data) {
  const box = $("#filters");
  const opts = [["all", "All"], ...ORDER.map((id) => [id, TASKS[id].name.split(" (")[0]])];
  for (const [id, lbl] of opts) {
    const b = el("button", id === "all" ? "on" : "", lbl);
    b.type = "button";
    b.setAttribute("aria-pressed", id === "all");
    b.onclick = () => {
      box.querySelectorAll("button").forEach((x) => { x.classList.toggle("on", x === b); x.setAttribute("aria-pressed", x === b); });
      renderAttempts(data, id);
    };
    box.append(b);
  }
  renderAttempts(data, "all");
}

function fit(stage) {
  const f = stage.querySelector("iframe");
  if (!f) return;
  const w = viewW(stage);
  f.width = w; f.height = Math.round(w * 10 / 16);
  f.style.transform = `scale(${stage.clientWidth / w})`;
}

function fill(stage, arm, g) {
  stage.textContent = "";
  const who = arm === "d" ? "written directly by Opus" : "written by the local model through Tandem";
  if (mode === "gif") {
    const img = el("img"); img.src = `gifs/${g[arm].replace("/", "_")}.gif`; img.alt = `${demo} page ${who}`; img.loading = "lazy";
    stage.append(img);
    return;
  }
  const f = el("iframe");
  f.src = `demos/${g[arm]}/index.html`; f.title = `${demo} page ${who}`; f.loading = "lazy";
  f.setAttribute("sandbox", "allow-scripts allow-same-origin");
  stage.append(f); fit(stage);
}

function showDemo() {
  const g = DEMOS[demo];
  fill($("#stage-d"), "d", g); fill($("#stage-t"), "t", g);
  $("#full-d").href = `demos/${g.d}/index.html`; $("#full-t").href = `demos/${g.t}/index.html`;
  $("#cap-d").textContent = g.cd; $("#cap-t").textContent = g.ct; $("#gif-note").textContent = g.note;
  document.querySelectorAll(".pick button").forEach((b) => {
    const on = b.dataset.demo ? b.dataset.demo === demo : b.dataset.mode === mode;
    b.classList.toggle("on", on); b.setAttribute("aria-pressed", on);
  });
}

fetch("data.json").then((r) => r.json()).then((data) => {
  renderKpis(data); renderTasks(data); renderTokens(data); renderFilters(data);
  $("#rule").textContent = data.rule.replace("every repetition", `all ${data.repeats} repeated evaluations`);
  $("#when").textContent = data.reevaluated_at.slice(0, 10);
}).catch((e) => { $("#kpis").textContent = "Could not load data.json: " + e; });
document.querySelectorAll(".pick button").forEach((b) => (b.onclick = () => {
  if (b.dataset.demo) demo = b.dataset.demo; else mode = b.dataset.mode;
  showDemo();
}));
window.addEventListener("resize", () => document.querySelectorAll(".stage").forEach(fit));
showDemo();
