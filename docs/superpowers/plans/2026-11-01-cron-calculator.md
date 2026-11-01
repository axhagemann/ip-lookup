# Cron Calculator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/cron` tool page that explains, schedules (next 5 runs, UTC), builds and converts cron expressions across six scheduler flavours.

**Architecture:** All logic lives in a new UMD module `static/cron-logic.js` (`window.CronCalc` in the browser, `require()` in Node tests), mirroring `static/cidr-logic.js`. `static/cron.html` is markup plus DOM wiring only. `main.py` gains one `FileResponse` route. Nothing runs on the server.

**Tech Stack:** Vanilla JS (ES2020, no deps), Node built-in test runner (`node --test`, Node 22 in CI), FastAPI + pytest for route/markup tests.

**Spec:** `docs/superpowers/specs/2026-11-01-cron-calculator-design.md`

## Global Constraints

- No npm dependencies, no CDN scripts, no build step, no new fonts/colours. Hand-written explainer and scheduler.
- Colours only via existing tokens in `static/style.css`; page `<style>` holds layout only. If `style.css` must change, bump `?v=N` on **every** page (currently `v=2`); prefer not to touch it.
- Page must include: color-scheme meta, `style.css?v=2`, `<script defer src="/theme.js?v=2">`, skip link, top bar with theme toggle, footer, GoatCounter snippet with `<noscript>` pixel `p=/cron` — copy from `static/cidr.html`.
- Mono (`.mono`) only for expressions, field values and computed times.
- Dynamic regions use `aria-live="polite"`; no `role="alert"` on live-as-you-type validation. Every control has a visible `<label>` (or `<legend>` for fieldsets).
- All times shown are UTC and labelled "All times are UTC."
- Input safety (spec section "Input safety"): 512-char cap, ASCII character allowlist, bounded parsing, and user-derived text reaches the DOM only via `textContent`/`value`/`createElement` — never `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `new Function`, or string `setTimeout`, in `cron.html` or `cron-logic.js`.
- English copy, 24-hour times.
- **Do not commit.** The user commits themselves; each task ends with changes left in the working tree.
- Python tooling: `source .venv/bin/activate` first; never install tools ad hoc. Node is not installed locally (CI runs `node --test` on Node 22). If `node` is unavailable, say so in the task report and rely on CI — do not install it.

## Review Focus

1. **Sloppy but valid input** — leading/trailing whitespace, tabs or multiple spaces between fields, lowercase names (`mon-fri`, `jan`) must parse. → Task 1 test `tolerates whitespace and lowercase names`.
2. **Unix weekday 7 and ranges ending in 7** (`0 0 * * 7`, `5-7`) mean Sunday and must survive conversion to 1-based flavours as `1`. → Task 1 test `unix dow 7 is sunday`, Task 4 test `unix 7 converts to quartz 1`.
3. **Expressions that run rarely or never** — `0 0 29 2 *` must find 29 Feb 2028 inside the search window; `0 0 31 4 *` returns `[]` without hanging. → Task 2 tests `leap day is found`, `impossible date never runs`.
4. **AWS input as people copy it** — `cron(0 12 * * ? *)`, with or without inner spaces. → Task 1 test `aws accepts cron() wrapper`.
5. **Reversed ranges** (`5-1`, `FRI-MON`) — rejected with a clear message naming the field, not silently empty. → Task 1 test `reversed range is an error`.

---

## File Structure

| File | Responsibility |
|---|---|
| `static/cron-logic.js` (create) | Flavour table, parse/validate, nextRuns, explain, convert, builder model |
| `static/cron.html` (create) | Page markup, page-only layout CSS, DOM wiring |
| `main.py` (modify) | `@app.get("/cron")` after the `/cidr` route |
| `static/index.html` (modify) | Fourth tool tile |
| `tests/cron_parse.test.js`, `cron_schedule.test.js`, `cron_explain.test.js`, `cron_convert.test.js`, `cron_builder.test.js` (create) | Node tests, one per concern |
| `tests/test_routes.py`, `tests/test_theme.py`, `tests/test_analytics.py` (modify) | Route + markup + snippet guards |
| `README.md`, `DESIGN.md` (modify) | Docs |

## Shared data model (used by every task)

Flavour ids: `"unix" | "kubernetes" | "github" | "quartz" | "aws" | "spring"`.

Field names: `"second" | "minute" | "hour" | "dom" | "month" | "dow" | "year"`.
Labels for messages: second, minute, hour, day of month, month, day of week, year.

```js
// Exported as CronCalc.FLAVOURS (array, in dropdown order)
{
  id: "quartz",
  label: "Quartz",
  fields: ["second","minute","hour","dom","month","dow","year"], // year optional for quartz only
  optionalYear: true,          // quartz only
  dowBase: 1,                  // 0 => 0-6 Sun=0 (unix/spring also accept 7=Sun); 1 => 1-7 Sun=1
  dowAllowsSeven: false,       // true for unix, spring
  question: "required",        // "none" | "alias" (? means *) | "required" (exactly one of dom/dow is ?)
  specials: true,              // L, W, #, LW, L-n allowed
  macros: [],                  // e.g. unix: ["@yearly","@annually","@monthly","@weekly","@daily","@midnight","@hourly","@reboot"]
  dayMatch: "single",          // "or" (Vixie: OR when both restricted) | "and" (spring) | "single" (one is ?)
  yearRange: [1970, 2099],     // aws: [1970, 2199]; null where no year field
  utcOnly: false,              // true for github, aws (drives the reinforced UTC note)
  minIntervalMinutes: null,    // github: 5
}
```

Values per flavour come from the spec's "Flavour rules" table. Kubernetes: `dowBase 0`, `dowAllowsSeven false`, `question "alias"`, macros without `@reboot`. Spring: `question "alias"`, `dayMatch "and"`, macros without `@reboot`. GitHub: `question "none"`, no macros, `minIntervalMinutes 5`.

Parsed result (`Cron`):

```js
{
  flavour: "unix",
  macro: null | "@daily" | ...,   // original macro token, fields are filled with its expansion
  reboot: false,                  // true only for @reboot; fields are null
  fields: { second, minute, hour, dom, month, dow, year },  // FieldSpec or null when the flavour lacks it
}
// FieldSpec
{
  raw: "1-5",                 // as typed (trimmed)
  star: false,                // raw starts with "*" (Vixie DOM_STAR rule, so "*/2" is star)
  question: false,            // raw === "?"
  values: [1,2,3,4,5],        // sorted unique, canonical numbering (dow: 0-6, Sun=0; 7 folded to 0)
  special: null,              // { type: "last", offset: 0 } dom L / L-n
                              // { type: "lastWeekday" }      dom LW
                              // { type: "nearestWeekday", day } dom 15W
                              // { type: "lastDow", dow }      dow 5L  (dow canonical)
                              // { type: "nthDow", dow, nth }  dow 6#3 (dow canonical)
}
```

A special is always the whole field (no `1,L`). Missing optional Quartz year ⇒ `year` is a star FieldSpec with `raw: "*"`.

---

### Task 1: Flavour table and parser

**Files:**
- Create: `static/cron-logic.js`
- Test: `tests/cron_parse.test.js`

**Interfaces:**
- Produces: `CronCalc.FLAVOURS`, `CronCalc.getFlavour(id) -> Flavour`, `CronCalc.parse(expr: string, flavourId: string) -> { ok: true, cron: Cron } | { ok: false, error: string, field: string | null }`.

- [ ] **Step 1: Write the failing tests** in `tests/cron_parse.test.js` (`require("../static/cron-logic.js")`, `node:test`, `node:assert/strict`, same style as `tests/cidr_logic.test.js`):

```js
test("unix basic", () => {
  const r = parse("0 9 * * 1-5", "unix");
  assert.equal(r.ok, true);
  assert.deepEqual(r.cron.fields.dow.values, [1,2,3,4,5]);
  assert.equal(r.cron.fields.second, null);
});
test("field count error names the order", () => {
  assert.deepEqual(parse("0 9 * *", "unix"), { ok: false, field: null,
    error: "Expected 5 fields (minute hour day-of-month month day-of-week), got 4." });
});
test("out of range names the field", () => {
  assert.deepEqual(parse("0 0 32 * *", "unix"), { ok: false, field: "dom",
    error: "Field 3 (day of month): 32 is out of range 1–31." });
});
test("special not supported by flavour", () => {
  assert.deepEqual(parse("0 0 L * *", "github"), { ok: false, field: "dom",
    error: "Field 3 (day of month): L is not supported by GitHub Actions." });
});
test("quartz needs exactly one ?", () => {
  assert.equal(parse("0 0 12 * * *", "quartz").error, "Quartz requires ? in exactly one of day of month and day of week.");
  assert.equal(parse("0 0 12 ? * ?", "quartz").ok, false);
  assert.equal(parse("0 0 12 * * ?", "quartz").ok, true);
});
test("quartz year is optional, aws year required", () => {
  assert.equal(parse("0 0 12 * * ? 2027", "quartz").ok, true);
  assert.equal(parse("0 12 * * ?", "aws").ok, false);
});
test("quartz dow is 1-based", () => {
  assert.deepEqual(parse("0 0 0 ? * 2", "quartz").cron.fields.dow.values, [1]); // Monday
});
test("specials parse", () => {
  const f = (e, fl) => parse(e, fl).cron.fields;
  assert.deepEqual(f("0 0 12 L * ?", "quartz").dom.special, { type: "last", offset: 0 });
  assert.deepEqual(f("0 0 12 L-3 * ?", "quartz").dom.special, { type: "last", offset: 3 });
  assert.deepEqual(f("0 0 12 LW * ?", "quartz").dom.special, { type: "lastWeekday" });
  assert.deepEqual(f("0 0 12 15W * ?", "quartz").dom.special, { type: "nearestWeekday", day: 15 });
  assert.deepEqual(f("0 0 12 ? * 6L", "quartz").dow.special, { type: "lastDow", dow: 5 });
  assert.deepEqual(f("0 0 12 ? * 6#3", "quartz").dow.special, { type: "nthDow", dow: 5, nth: 3 });
});
test("macros expand and @reboot has no fields", () => {
  const d = parse("@daily", "unix").cron;
  assert.equal(d.macro, "@daily");
  assert.deepEqual(d.fields.hour.values, [0]);
  assert.equal(parse("@reboot", "unix").cron.reboot, true);
  assert.equal(parse("@reboot", "kubernetes").ok, false);
  assert.equal(parse("@daily", "github").ok, false);
});
test("kubernetes rejects TZ prefix", () => {
  assert.equal(parse("CRON_TZ=Europe/Berlin 0 9 * * *", "kubernetes").error,
    "Time zone prefixes aren't supported in the schedule; set spec.timeZone on the CronJob instead.");
});
test("steps, lists, start/step", () => {
  assert.deepEqual(parse("*/15 * * * *", "unix").cron.fields.minute.values, [0,15,30,45]);
  assert.deepEqual(parse("0 5/20 * * * ?", "quartz").cron.fields.minute.values, [5,25,45]);
  assert.equal(parse("*/2 * * * *", "unix").cron.fields.minute.star, true);
});
test("empty input", () => {
  assert.deepEqual(parse("   ", "unix"), { ok: false, field: null, error: "Enter a cron expression." });
});
// Review Focus
test("tolerates whitespace and lowercase names", () => {
  const r = parse("  0\t9  *  jan,feb mon-fri ", "unix");
  assert.equal(r.ok, true);
  assert.deepEqual(r.cron.fields.month.values, [1,2]);
  assert.deepEqual(r.cron.fields.dow.values, [1,2,3,4,5]);
});
test("unix dow 7 is sunday", () => {
  assert.deepEqual(parse("0 0 * * 7", "unix").cron.fields.dow.values, [0]);
  assert.deepEqual(parse("0 0 * * 5-7", "unix").cron.fields.dow.values, [0,5,6]);
  assert.equal(parse("0 0 * * 7", "github").ok, false);
});
test("aws accepts cron() wrapper", () => {
  assert.equal(parse("cron(0 12 * * ? *)", "aws").ok, true);
  assert.equal(parse("  cron( 0 12 * * ? * )  ", "aws").ok, true);
});
test("reversed range is an error", () => {
  assert.deepEqual(parse("0 0 * * 5-1", "unix"), { ok: false, field: "dow",
    error: "Field 5 (day of week): range 5-1 starts after it ends." });
  assert.equal(parse("0 0 * * FRI-MON", "unix").ok, false);
});
// Input safety
test("length cap", () => {
  assert.deepEqual(parse("0 ".repeat(300), "unix"), { ok: false, field: null,
    error: "Expression is too long (max 512 characters)." });
});
test("character allowlist", () => {
  assert.deepEqual(parse("0 9 * * <script>", "unix"), { ok: false, field: null,
    error: 'Unsupported character "<" at position 9.' });
  assert.equal(parse("0 9 * * 1;rm", "unix").ok, false);
  assert.equal(parse("0 9 * * $(id)", "unix").ok, false);
  assert.equal(parse("0 9 * * 1\n2", "unix").ok, false);
  assert.equal(parse("０ 9 * * *", "unix").ok, false);              // full-width digit
  assert.equal(parse("0 9 * * *", "unix").ok, false);           // non-breaking space
  assert.match(parse("0 9​ * * *", "unix").error, /U\+200B/);  // zero-width shown as code
  assert.equal(parse("0 9 * * 1-5\n", "unix").ok, true);             // trailing newline from paste is trimmed
});
test("step zero is an error", () => {
  assert.deepEqual(parse("*/0 * * * *", "unix"), { ok: false, field: "minute",
    error: "Field 1 (minute): step must be at least 1." });
});
test("bounded tokens", () => {
  assert.equal(parse("00000000001 * * * *", "unix").ok, false);            // > 4 digits
  assert.equal(parse(Array(65).fill("1").join(",") + " * * * *", "unix").ok, false); // > 64 items
});
test("echoed tokens are truncated", () => {
  const r = parse("0 0 ABCDEFGHIJKLMNOPQRSTUVWXYZ * *", "unix");
  assert.equal(r.ok, false);
  assert.ok(!r.error.includes("ABCDEFGHIJKLMNOPQRSTUVWXYZ"));
  assert.ok(r.error.includes("…"));
});
test("pathological input stays fast", () => {
  const t = Date.now();
  parse("1-".repeat(255), "unix");
  parse(",".repeat(511), "quartz");
  assert.ok(Date.now() - t < 50);
});
```

- [ ] **Step 2: Run to verify failure** — `node --test tests/cron_parse.test.js` → FAIL (`Cannot find module`).

- [ ] **Step 3: Implement** the UMD wrapper (copy the header pattern from `cidr-logic.js`, attach `root.CronCalc`), `FLAVOURS` per the shared data model, `getFlavour`, and `parse`. Order of checks: trim → empty → length cap (512) → character allowlist (`/^[A-Za-z0-9 \t*?,\-\/#@()_=]*$/`, report first offender with 1-based position; invisible/non-printable shown as `U+XXXX`) → strip `cron(...)` (aws only) → TZ prefix (any flavour: same message for kubernetes, generic "Time zone prefixes aren't supported." elsewhere) → macro → split on `/[ \t]+/` (not `\s`) → field count (Quartz accepts 6 or 7) → per field: ≤ 64 comma items, numbers ≤ 4 digits, step ≥ 1, echoed tokens truncated to 20 chars + "…" → tokens (`,` list of `*`, `?`, `n`, `a-b`, `*/n`, `a/n`, `a-b/n`, names case-insensitive `JAN–DEC`/`SUN–SAT`, specials) → range check in the flavour's numbering → fold dow to canonical → `?` rule. Field position in messages is 1-based in the typed order. Before finishing, check the ⚠ rows of the spec's flavour table against official docs (robfig/cron v3 for Kubernetes, Spring `CronExpression` javadoc); if a doc contradicts the table, follow the doc and note it in the task report.

- [ ] **Step 4: Run** — `node --test tests/cron_parse.test.js` → all PASS.

- [ ] **Step 5: Leave uncommitted.**

---

### Task 2: Next runs (UTC)

**Files:**
- Modify: `static/cron-logic.js`
- Test: `tests/cron_schedule.test.js`

**Interfaces:**
- Consumes: `parse`, `Cron`.
- Produces: `CronCalc.nextRuns(cron: Cron, from: Date, n = 5) -> Date[]` — strictly after `from`, UTC, `[]` for `@reboot` or nothing found within the window.

- [ ] **Step 1: Write failing tests** (helper `iso = (e, fl, from, n) => nextRuns(parse(e, fl).cron, new Date(from), n).map(d => d.toISOString())`):

```js
test("weekdays at 09:00", () => assert.deepEqual(iso("0 9 * * 1-5", "unix", "2026-11-06T10:00:00Z", 3),
  ["2026-11-09T09:00:00.000Z","2026-11-10T09:00:00.000Z","2026-11-11T09:00:00.000Z"]));
test("strictly after from", () => assert.deepEqual(iso("0 9 * * *", "unix", "2026-11-06T09:00:00Z", 1), ["2026-11-07T09:00:00.000Z"]));
test("seconds", () => assert.deepEqual(iso("30 0 12 * * ?", "quartz", "2026-11-01T00:00:00Z", 1), ["2026-11-01T12:00:30.000Z"]));
test("vixie OR when both restricted", () => assert.deepEqual(iso("0 0 1 * 1", "unix", "2026-11-01T00:00:00Z", 3),
  ["2026-11-02T00:00:00.000Z","2026-11-09T00:00:00.000Z","2026-11-16T00:00:00.000Z"]));  // + Dec 1 later
test("vixie star-step dom means AND", () => assert.deepEqual(iso("0 0 */2 * 1", "unix", "2026-11-01T00:00:00Z", 2),
  ["2026-11-09T00:00:00.000Z","2026-11-23T00:00:00.000Z"]));  // odd days that are Mondays
test("spring AND", () => assert.deepEqual(iso("0 0 0 13 * FRI", "spring", "2026-01-01T00:00:00Z", 1), ["2026-02-13T00:00:00.000Z"]));
test("last day", () => assert.deepEqual(iso("0 0 12 L * ?", "quartz", "2026-02-01T00:00:00Z", 1), ["2026-02-28T12:00:00.000Z"]));
test("L-3", () => assert.deepEqual(iso("0 0 12 L-3 * ?", "quartz", "2026-11-01T00:00:00Z", 1), ["2026-11-27T12:00:00.000Z"]));
test("nearest weekday stays in month", () => assert.deepEqual(iso("0 0 12 1W * ?", "quartz", "2026-11-01T00:00:00Z", 1), ["2026-11-02T12:00:00.000Z"])); // Nov 1 2026 is Sunday
test("LW", () => assert.deepEqual(iso("0 0 12 LW * ?", "quartz", "2026-01-01T00:00:00Z", 1), ["2026-01-30T12:00:00.000Z"])); // Jan 31 2026 is Saturday
test("nth weekday", () => assert.deepEqual(iso("0 0 10 ? * 6#3", "quartz", "2026-11-01T00:00:00Z", 1), ["2026-11-20T10:00:00.000Z"]));
test("last friday", () => assert.deepEqual(iso("0 0 10 ? * 6L", "quartz", "2026-11-01T00:00:00Z", 1), ["2026-11-27T10:00:00.000Z"]));
test("aws year", () => assert.deepEqual(iso("0 12 1 1 ? 2028", "aws", "2026-11-01T00:00:00Z", 2), ["2028-01-01T12:00:00.000Z"]));
test("@reboot has no runs", () => assert.deepEqual(iso("@reboot", "unix", "2026-11-01T00:00:00Z", 5), []));
// Review Focus
test("leap day is found", () => assert.deepEqual(iso("0 0 29 2 *", "unix", "2026-11-01T00:00:00Z", 1), ["2028-02-29T00:00:00.000Z"]));
test("impossible date never runs", () => assert.deepEqual(iso("0 0 31 4 *", "unix", "2026-11-01T00:00:00Z", 5), []));
```

- [ ] **Step 2: Run** — `node --test tests/cron_schedule.test.js` → FAIL.

- [ ] **Step 3: Implement `nextRuns`.** Day-first search, not minute stepping:

```
for each UTC day from from's date, up to 5 years ahead (≈1830 days):
  skip unless year ∈ year.values (when present) and month ∈ month.values
  skip unless dayMatches(day)
  for h in hour.values, m in minute.values, s in (second?.values ?? [0]):
    t = Date.UTC(y, mo-1, d, h, m, s); if t > from: push; return when n reached
dayMatches:
  domOk = special ? specialDom(day) : dom.values has d
  dowOk = special ? specialDow(day) : dow.values has weekday
  "single": use whichever of dom/dow is not question (? side ignored)
  "and":    domOk && dowOk
  "or":     if dom.star || dow.star → domOk && dowOk  (star side matches everything)
            else domOk || dowOk
```

Nearest weekday never crosses month boundaries (Sat 1st → Mon 3rd; Sun last → Fri). `?` alias (kubernetes/spring) counts as star.

- [ ] **Step 4: Run** — PASS.

- [ ] **Step 5: Leave uncommitted.**

---

### Task 3: Explainer

**Files:**
- Modify: `static/cron-logic.js`
- Test: `tests/cron_explain.test.js`

**Interfaces:**
- Consumes: `parse`, `Cron`.
- Produces: `CronCalc.explain(cron: Cron) -> string` (one sentence, ends with ".").

- [ ] **Step 1: Write failing tests** — table-driven, `explain(parse(e, fl).cron)` equals:

| Expression | Flavour | Expected |
|---|---|---|
| `* * * * *` | unix | `Every minute.` |
| `*/15 * * * *` | unix | `Every 15 minutes.` |
| `0 * * * *` | unix | `At minute 0 of every hour.` |
| `0 */2 * * *` | unix | `At minute 0 past every 2nd hour.` |
| `0 9 * * 1-5` | unix | `At 09:00, Monday through Friday.` |
| `30 2 1 * *` | unix | `At 02:30, on day 1 of the month.` |
| `0 0 * * 0` | unix | `At 00:00, on Sunday.` |
| `0 12 * 1,6 *` | unix | `At 12:00, in January and June.` |
| `0 0 1 * 1` | unix | `At 00:00, on day 1 of the month or on Monday.` |
| `0 0 0 13 * FRI` | spring | `At 00:00, on day 13 of the month if it is a Friday.` |
| `30 0 12 * * ?` | quartz | `At 12:00:30.` |
| `0 0 12 L * ?` | quartz | `At 12:00, on the last day of the month.` |
| `0 0 12 L-3 * ?` | quartz | `At 12:00, 3 days before the last day of the month.` |
| `0 0 12 15W * ?` | quartz | `At 12:00, on the weekday nearest day 15 of the month.` |
| `0 0 12 LW * ?` | quartz | `At 12:00, on the last weekday of the month.` |
| `0 0 10 ? * 6#3` | quartz | `At 10:00, on the third Friday of the month.` |
| `0 0 10 ? * 6L` | quartz | `At 10:00, on the last Friday of the month.` |
| `0 12 * * ? 2027` | aws | `At 12:00, in 2027.` |
| `0 9,17 * * *` | unix | `At 09:00 and 17:00.` |
| `@reboot` | unix | `At system startup.` |

- [ ] **Step 2: Run** — `node --test tests/cron_explain.test.js` → FAIL.

- [ ] **Step 3: Implement `explain`** as `[timePart, dayPart, monthPart, yearPart].filter(Boolean).join(", ") + "."`. Time part lists up to 4 concrete `HH:MM[:SS]` when hour and minute (and second) are each a short list; otherwise falls back to the minute/hour phrases above. Lists join with ", " and final " and "; contiguous ranges render "X through Y". Wording beyond the table is the implementer's call.

- [ ] **Step 4: Run** — PASS.

- [ ] **Step 5: Leave uncommitted.**

---

### Task 4: Converter

**Files:**
- Modify: `static/cron-logic.js`
- Test: `tests/cron_convert.test.js`

**Interfaces:**
- Consumes: `parse`, `getFlavour`.
- Produces: `CronCalc.convert(expr: string, fromId: string, toId: string) -> { ok: true, expression: string, warnings: string[] } | { ok: false, error: string }`.

- [ ] **Step 1: Write failing tests** — one per row of the spec's conversion policy table:

```js
const ok = (e, f, t) => { const r = convert(e, f, t); assert.equal(r.ok, true, r.error); return r; };
test("unix → quartz renumbers dow and adds ? and seconds", () =>
  assert.equal(ok("0 9 * * 1-5", "unix", "quartz").expression, "0 0 9 ? * 2-6"));
test("names stay names", () => assert.equal(ok("0 9 * * MON-FRI", "unix", "quartz").expression, "0 0 9 ? * MON-FRI"));
test("unix 7 converts to quartz 1", () => assert.equal(ok("0 0 * * 7", "unix", "quartz").expression, "0 0 0 ? * 1"));
test("dow step becomes explicit list", () => assert.equal(ok("0 0 * * */2", "unix", "quartz").expression, "0 0 0 ? * 1,3,5,7"));
test("dom restricted gets ? in dow", () => assert.equal(ok("0 0 1 * *", "unix", "aws").expression, "cron(0 0 1 * ? *)"));
test("both restricted refuses for quartz/aws", () => {
  const r = convert("0 0 1 * 1", "unix", "quartz");
  assert.equal(r.ok, false);
  assert.match(r.error, /split it into two schedules/);
});
test("? becomes * for unix", () => assert.equal(ok("0 0 12 ? * MON", "quartz", "unix").expression, "0 12 * * MON"));
test("fixed seconds dropped with warning", () => {
  const r = ok("30 0 12 * * ?", "quartz", "unix");
  assert.equal(r.expression, "0 12 * * *");
  assert.deepEqual(r.warnings, ["Unix cron has no seconds field, so this will run at :00 instead of :30."]);
});
test("sub-minute seconds refuse", () => assert.equal(convert("*/10 * * * * ?", "quartz", "unix").ok, false));
test("specific year refuses for yearless target", () => assert.equal(convert("0 12 1 1 ? 2028", "aws", "unix").ok, false));
test("star year dropped silently", () => assert.deepEqual(ok("0 12 * * ? *", "aws", "github").warnings, []));
test("L to unix refuses naming token", () => assert.match(convert("0 0 12 L * ?", "quartz", "unix").error, /\bL\b/));
test("macro expands when target has none", () => assert.equal(ok("@daily", "unix", "quartz").expression, "0 0 0 * * ?"));
test("macro kept when target supports it", () => assert.equal(ok("@daily", "unix", "kubernetes").expression, "@daily"));
test("@reboot refuses", () => assert.equal(convert("@reboot", "unix", "kubernetes").ok, false));
test("start/step rewritten for unix family", () => assert.equal(ok("0 5/20 * * * ?", "quartz", "unix").expression, "5-59/20 * * * *"));
test("github 5-minute warning", () => {
  assert.equal(ok("*/2 * * * *", "unix", "github").warnings.length, 1);
  assert.deepEqual(ok("*/5 * * * *", "unix", "github").warnings, []);
});
test("same flavour unchanged", () => assert.equal(ok("0 9 * * 1-5", "unix", "unix").expression, "0 9 * * 1-5"));
test("invalid source returns parse error", () => assert.equal(convert("0 0 32 * *", "unix", "quartz").ok, false));
```

- [ ] **Step 2: Run** — `node --test tests/cron_convert.test.js` → FAIL.

- [ ] **Step 3: Implement `convert`.** Parse with `fromId`, then check refusals (reboot, OR-day → `single` target, specials → non-special target, sub-minute seconds, specific year → yearless target), then build the target's fields from the **raw** source field strings so the user's notation survives: dow numeric tokens shifted by `target.dowBase - source.dowBase` (7 → Sunday's target number), dow fields containing `/` re-emitted as an explicit comma list in target numbering, `a/n` → `a-max/n` for targets without start/step support (unix, kubernetes, github), `?` ↔ `*` per `target.question`, seconds `0` added/fixed seconds dropped, year `*` added for aws (and omitted for quartz). Refusal messages state the reason in one sentence; the OR-day one must contain "split it into two schedules". GitHub interval warning: warn when the minute value set has two cyclically adjacent values less than 5 apart (with wrap-around `60 - last + first` counted only if hour is not a single value); copy: "GitHub Actions won't run schedules more often than every 5 minutes." Wrap aws output as `cron(...)`. Finally re-parse the output with `toId` and throw if it fails (bug guard; should never fire in tests).

- [ ] **Step 4: Run** — PASS, plus `node --test` (all files) PASS.

- [ ] **Step 5: Leave uncommitted.**

---

### Task 5: Builder model

**Files:**
- Modify: `static/cron-logic.js`
- Test: `tests/cron_builder.test.js`

**Interfaces:**
- Consumes: `parse`, `getFlavour`.
- Produces:
  - `CronCalc.toBuilder(cron: Cron) -> { [fieldName]: BuilderField }` (only the flavour's fields; Quartz always includes `year`).
  - `CronCalc.fromBuilder(builder, flavourId) -> string`.
  - `CronCalc.builderModes(fieldName, flavourId) -> string[]` — modes the UI may offer.
  - `BuilderField = { mode: "every" } | { mode: "step", start, step } | { mode: "specific", values: number[] } | { mode: "range", from, to } | { mode: "none" } | { mode: "last", offset? , dow? } | { mode: "weekday", day: number | "L" } | { mode: "nth", dow, nth } | { mode: "custom", raw: string }`. Dow numbers in models are canonical (0–6, Sun=0); `fromBuilder` writes the flavour's numbering.

- [ ] **Step 1: Write failing tests:**

```js
test("round trip simple", () => {
  for (const [e, fl] of [["0 9 * * 1-5","unix"],["*/15 * * * *","unix"],["0 0 10 ? * 6#3","quartz"],["0 0 12 L * ?","quartz"],["0 12 * * ? *","aws"]])
    assert.equal(fromBuilder(toBuilder(parse(e, fl).cron), fl), e);
});
test("modes", () => {
  const b = toBuilder(parse("0 9 * * 1-5", "unix").cron);
  assert.deepEqual(b.minute, { mode: "specific", values: [0] });
  assert.deepEqual(b.dow, { mode: "range", from: 1, to: 5 });
  assert.deepEqual(b.hour.mode, "specific");
});
test("unrepresentable field is custom", () =>
  assert.deepEqual(toBuilder(parse("1-5,10-20/2 * * * *", "unix").cron).minute, { mode: "custom", raw: "1-5,10-20/2" }));
test("macro expands into fields", () => assert.deepEqual(toBuilder(parse("@hourly", "unix").cron).minute, { mode: "specific", values: [0] }));
test("start/step writes flavour syntax", () => {
  const b = toBuilder(parse("*/5 * * * *", "unix").cron);
  b.minute = { mode: "step", start: 3, step: 10 };
  assert.equal(fromBuilder(b, "unix"), "3-59/10 * * * *");
});
test("builder dow written in flavour numbering", () => {
  const b = toBuilder(parse("0 0 0 ? * *", "quartz").cron);
  b.dow = { mode: "specific", values: [1] };   // Monday
  b.dom = { mode: "none" };
  assert.equal(fromBuilder(b, "quartz"), "0 0 0 ? * 2");
});
test("modes offered per flavour", () => {
  assert.deepEqual(builderModes("dom", "github"), ["every","step","specific","range","custom"]);
  assert.deepEqual(builderModes("dom", "quartz"), ["every","step","specific","range","none","last","weekday","custom"]);
  assert.deepEqual(builderModes("dow", "aws"), ["every","step","specific","range","none","last","nth","custom"]);
});
```

- [ ] **Step 2: Run** — `node --test tests/cron_builder.test.js` → FAIL.

- [ ] **Step 3: Implement.** `toBuilder` classifies each field's raw text: `*` → every; `*/n` or `a/n` or `a-max/n` → step; plain comma numbers/names → specific; single `a-b` → range; `?` → none (`?` in alias flavours → every); specials → last/weekday/nth; anything else → custom. `@reboot` returns `null` (UI shows a note instead of the builder). `fromBuilder` omits the Quartz year when its mode is `every` (so 6-field Quartz round-trips); AWS always writes it.

- [ ] **Step 4: Run** — `node --test` → all PASS.

- [ ] **Step 5: Leave uncommitted.**

---

### Task 6: Route, page shell, explanation + next runs

**Files:**
- Create: `static/cron.html`
- Modify: `main.py` (new route directly after `cidr()`), `static/index.html` (tile after the CIDR tile)
- Test: `tests/test_routes.py`, `tests/test_theme.py`, `tests/test_analytics.py`

**Interfaces:**
- Consumes: `CronCalc.FLAVOURS`, `parse`, `explain`, `nextRuns`.
- Produces: element ids later tasks wire into: `cron-form`, `flavour-select`, `expr-input`, `field-hint`, `expr-error`, `result`, `explanation`, `next-runs`, `utc-note`, `builder`, `target-select`, `convert-btn`, `convert-result`, `convert-output`, `copy-btn`, `copy-status`, `convert-warnings`, `convert-error`.

- [ ] **Step 1: Write failing pytest tests:**
  - `tests/test_routes.py::test_cron_serves_html` — `/cron` 200, `text/html`, `"Cron" in res.text`.
  - `tests/test_theme.py`: add `"/cron"` to the `test_routes_serve_themed_pages_and_their_assets` parametrize list; change `test_every_page_is_themed` to `== 8`; add `test_cron_keeps_script_hooks_and_labels` asserting every id above is present, `'<label for="flavour-select">'`, `'<label for="expr-input">'`, `'<label for="target-select">'`, `'<script src="/cron-logic.js"></script>'`, `'id="expr-error" aria-live="polite"'`, `"All times are UTC."`, and that `'role="alert"'` does **not** appear on `expr-error`.
  - `tests/test_analytics.py`: add `"cron.html": "/cron"` to `PAGES`.
  - `tests/test_theme.py::test_cron_has_no_html_injection_sinks` — for both `static/cron.html` and `static/cron-logic.js`, assert none of `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval(`, `new Function` appear, and `re.search(r"setTimeout\(\s*['\"`]", text)` is `None`; assert `'maxlength="512"'` is on `#expr-input`.

- [ ] **Step 2: Run** — `source .venv/bin/activate && python -m pytest` → the new/changed tests FAIL (404 / missing file).

- [ ] **Step 3: Implement.**
  - `main.py`: `@app.get("/cron")` → `FileResponse("static/cron.html")`, same shape as `cidr()`.
  - `static/index.html`: tile `<a class="card tool-link" href="/cron">` with `<h2>Cron Calculator</h2>` and a one-line description ("Explain, build and convert cron expressions for Unix, Quartz, AWS, Spring, Kubernetes and GitHub Actions, with the next run times.").
  - `static/cron.html`: copy head/top bar/footer/analytics from `cidr.html` (title "Cron Expression Calculator", meta description, pixel `p=/cron`). `h1` "Cron expression calculator" + `.description`. First `.card` holds `<form id="cron-form" novalidate>` with the flavour `<select>` (options from `FLAVOURS`, built in JS or hard-coded — must match ids) and the mono expression input (`maxlength="512"`, `autocomplete="off"`, `spellcheck="false"`); `#field-hint` (mono, `.note`) shows the flavour's field order; `<p class="error" id="expr-error" aria-live="polite">`; `<div class="result" id="result" aria-live="polite" hidden>` containing `#explanation`, a "Next 5 runs" heading, `<ol id="next-runs" class="mono">`, `<p class="note" id="utc-note">All times are UTC.</p>`. Placeholder/empty `#builder` card and convert card markup with the ids above (wired in Task 7).
  - Script: on `input` of `#expr-input` and `change` of `#flavour-select` → `parse`; empty input hides both result and error; invalid shows error, hides result; valid shows `explain` text and `nextRuns(cron, new Date(), 5)` formatted `YYYY-MM-DD HH:MM[:SS] UTC` (seconds only for flavours with a seconds field); `[]` shows "This expression never runs." (or "Runs at system startup only." for `@reboot`). For `utcOnly` flavours append to `#utc-note`: "GitHub Actions always runs schedules in UTC." / "EventBridge rules always run in UTC." Prefill `0 9 * * 1-5` with Unix so the page isn't empty.

- [ ] **Step 4: Run** — `python -m pytest` PASS, `ruff check .` clean. Manual: `uvicorn main:app --reload --port 8000`, open `/cron`, type valid/invalid expressions in both themes; check keyboard order and that the error is announced (screen reader or devtools accessibility pane).

- [ ] **Step 5: Leave uncommitted.**

---

### Task 7: Builder and convert UI

**Files:**
- Modify: `static/cron.html`

**Interfaces:**
- Consumes: Task 6 ids; `toBuilder`, `fromBuilder`, `builderModes`, `convert`, `FLAVOURS`.

- [ ] **Step 1: Extend `test_cron_keeps_script_hooks_and_labels`** (or add `test_cron_builder_and_convert_wiring`) asserting the page references `CronCalc.toBuilder`, `fromBuilder`, `builderModes`, `convert`, uses `<fieldset` and `<legend` in builder rendering code, and `id="copy-status" aria-live="polite"`. Run `python -m pytest tests/test_theme.py` → FAIL.

- [ ] **Step 2: Implement the builder.** Render one `<fieldset>`/`<legend>` per field of the selected flavour into `#builder`; inside, a labelled mode `<select>` (options from `builderModes`, human labels: Every, Every N, Specific values, Range, No specific value (?), Last, Nearest weekday, Nth weekday, Custom) and labelled inputs for that mode (numbers via `<input type="number">` with min/max; day-of-week and month specific values via labelled checkboxes or a multi-entry text input — implementer's call, must be keyboard-operable). Any builder change → `fromBuilder` → write `#expr-input` → re-run the Task 6 update. Typing in `#expr-input` → if valid, `toBuilder` and re-render (preserve focus: don't re-render while focus is inside `#builder`). `@reboot` → replace builder with a `.note` "@reboot has no schedule to build."
- [ ] **Step 3: Flavour switch.** Remember the previous flavour; on change, if the expression parses under the new flavour keep it; else `convert(expr, prev, next)` — on success replace the expression and show its warnings in `#expr-error`'s neighbour as a `.note` list; on failure show the conversion error in `#expr-error`. Then rebuild builder and hint.
- [ ] **Step 4: Convert card.** `#target-select` (all flavours, default the first one different from the source) + `#convert-btn` (`.btn btn-primary`). Result in `#convert-result` (`aria-live="polite"`): `#convert-output` (mono), `#copy-btn` (`.btn btn-secondary`, `navigator.clipboard.writeText`, falls back to selecting the text) writing "Copied" into `#copy-status`; warnings as `<ul id="convert-warnings">`; refusals in `<p class="error" id="convert-error">`. Disable the button while the source expression is invalid.
- [ ] **Step 5: Run** — `python -m pytest`, `ruff check .`, `node --test` PASS. Manual in both themes at 320px width and desktop: build `0 9 * * 1-5` from scratch with the keyboard only; switch Unix → Quartz → GitHub with `0 0 1 * 1` (expect refusal on Quartz); convert `30 0 12 * * ?` Quartz → Unix and see the seconds warning; copy works and is announced.
- [ ] **Step 6: Leave uncommitted.**

---

### Task 8: Docs and final verification

**Files:**
- Modify: `README.md` (new "## Cron Calculator" section after "## CIDR Calculator", tests line at ~129 to mention `cron-logic.js`, file tree at ~399–404), `DESIGN.md` (mono list at line 78: add cron expressions and run times)

- [ ] **Step 1: Update docs** — README section: served at `/cron`, flavours supported, client-side only, next runs in UTC, conversion warns/refuses on lossy changes.
- [ ] **Step 2: Full verification** — `source .venv/bin/activate && ruff check . && ruff format --check . && python -m pytest` → all PASS; `node --test` → all PASS (or report Node unavailable locally; CI runs it).
- [ ] **Step 3: Accessibility review** — run the `ux-accessibility-reviewer` agent on `static/cron.html`; fix any WCAG 2.1 AA findings.
- [ ] **Step 4: Manual safety check** — in the browser paste `<img src=x onerror=alert(1)>`, `0 0 * * 1‮` (right-to-left override), a 10 000-char string, and `*/0 * * * *`: expect a plain-text error each time, no alert, no layout break, no freeze; the 10 000-char paste is truncated to 512 by `maxlength`.
- [ ] **Step 5: Leave uncommitted;** summarise changed files for the user.
