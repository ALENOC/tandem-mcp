"use strict";

const TASKS = {
  py_discount: { name: "5-line bug fix", kind: "Python edit",
    why: "3/3 on both arms; Tandem costs 8% more on an edit this small (10% in 4.0.0), so the guide routes edits under about 30 lines direct." },
  py_cron: { name: "Cron parser module with tests", kind: "Python module",
    why: "Tandem lost pair 2: the local job ran out of time twice (the job_continue hint opened a second window), then Opus patched the file itself, 31 minutes over budget." },
  web_boids: { name: "Boids web simulation", kind: "Web page",
    why: "3/3 on both arms, all at 60 FPS. Pair 2 Tandem ended blocked on a broken check in Opus's contract, but the local page passes. The 2 local VLM strikes (pair 1) were false positives." },
  gen_orbital: { name: "Orbital web simulation", kind: "Web page",
    why: "1/3 on both arms; the evaluator's interaction checks fail most pages of both arms. Direct pair 1 lost 82 minutes to a cloud API stall (its page passes). Opus sent 2 visual hints after seeing the screenshot." },
  gen_portal: { name: "3D neon portal (4 files)", kind: "3D web app",
    why: "No Direct portal passed (interactions or visual). Tandem pair 2 passed at 60 FPS after one visual hint; pair 1 got stuck and Opus patched it (still failing, 12 FPS)." },
};
const ORDER = ["py_discount", "py_cron", "web_boids", "gen_orbital", "gen_portal"];
const RUN_TAG = () => "";
const DEMOS = {
  orbital: { d: "orbital/direct", t: "orbital/tandem", cd: "pair 3 · passed · $0.30 · 86 s", ct: "pair 3 · passed · $0.16 · 14 min",
    note: "Same pair, the only one where both arms pass. Both run at 60 FPS. Direct adds polish not asked for (glow halos, ringed planet, usage hint); Tandem is plainer, with a HUD fixed by one Opus hint after the screenshot." },
  portal: { d: "portal/direct", t: "portal/tandem", cd: "pair 2 · failed (interactions) · $0.59 · 134 s", ct: "pair 2 · passed · $0.15 · 40 min",
    note: "Same pair; Tandem pair 2 is the only portal of either arm that passed. Both run at 60 FPS. Direct's scene is richer and fills the frame but fails interactions; Tandem's is correct but small and plain." },
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
  $("#note-punctual").innerHTML = `<b>Trade-off and caveats:</b> Tandem is about 12x slower (median 11 to 33 min against 1 to 2.5 min on medium and large tasks). Small edits cost 8% more and stay direct. Without the 82-minute API stall on Direct Orbital: $0.202 vs $0.394 (-49%). The late Tandem Cron counted under "ignoring budget" was patched by Opus after the local job ran out of time; Tandem Portal pair 1 was also patched by Opus and still failed. 3 pairs per task: a 1-success gap is not decisive.`;
}

function renderTasks(data) {
  const box = $("#task-cards");
  for (const id of ORDER) {
    const s = data.summary[id], info = TASKS[id];
    // when one arm has no success, compare both arms per attempt, never per success against per attempt
    const perAttempt = s.direct.cost_usd_per_success == null || s.tandem.cost_usd_per_success == null;
    const metric = (a) => perAttempt ? s[a].cost_usd_total / s[a].attempts : s[a].cost_usd_per_success;
    const max = Math.max(metric("direct"), metric("tandem"));
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
      const cost = perAttempt ? `<b>${usd(metric(arm))}</b> per attempt` + (a.cost_usd_per_success == null ? "" : ` (${usd(a.cost_usd_per_success)} per success)`) : `<b>${usd(a.cost_usd_per_success)}</b> per success`;
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
    if (a.arm === "tandem" && a.local_jobs && a.local_jobs.length) dl += `<dt>Local job</dt><dd>${a.local_jobs.join(", ")}</dd>`;
    if (a.hints) dl += `<dt>Opus hints</dt><dd>${a.hints}</dd>`;
    if (a.visual_review && a.visual_review.length) dl += `<dt>VLM review</dt><dd>${a.visual_review.join(", ")}${a.visual_strikes ? ` (${a.visual_strikes} strikes)` : ""}</dd>`;
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
