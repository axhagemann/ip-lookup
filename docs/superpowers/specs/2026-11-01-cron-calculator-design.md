# Cron Calculator — Design

**Date:** 2026-11-01
**Status:** Draft, awaiting approval
**Scope:** new `static/cron.html`, new `static/cron-logic.js`, `/cron` route in `main.py`, tile in `static/index.html`, tests, README

## Intent

A fourth tool on the site for the three moments someone reaches for a cron tool:

1. **Setting up** a job — build an expression field by field without remembering the syntax.
2. **Debugging** an expression — paste it, read in plain English what it does, see when it will actually run.
3. **Migrating** a job — convert an expression from one scheduler's dialect to another's, and be told clearly what doesn't carry over.

It must look and behave like the existing tools (light-first, OS-theme-following, WCAG 2.1 AA) and, like the CIDR calculator, run entirely in the browser.

## Goals

- Flavour dropdown: **Unix (Vixie/cronie)**, **Quartz**, **AWS EventBridge**, **Spring**, **Kubernetes CronJob**, **GitHub Actions**.
- Expression input that validates as you type, against the selected flavour's rules, with errors that name the offending field.
- Plain-English explanation of a valid expression.
- Next 5 run times, **in UTC**, with a visible note saying they are UTC.
- A builder: one control group per field, two-way synced with the expression input.
- Conversion to a target flavour, with a copy button and a list of warnings/blocking reasons.

## Non-goals (v1)

- Time zone selection for next runs (UTC only, labelled). May come later; DST handling is the reason it's deferred.
- AWS `rate(...)` expressions, `at(...)` one-time schedules, EventBridge Scheduler time zones.
- Shareable URLs with the expression in the query string (would also put expressions into analytics paths).
- An examples/presets gallery.
- Any server round-trip — no new API endpoint.

## Anti-goals (failure even if it "works")

- A conversion that silently changes when a job runs. Every lossy step is either a visible warning or a refusal.
- Accepting syntax a flavour would reject (e.g. `L` for GitHub Actions) and explaining it as if valid.
- New colours, fonts, libraries, CDN scripts or a build step.

## Constraints (from the repo)

- Follows the "new tool page" pattern in CLAUDE.md: `static/cron.html`, `@app.get("/cron")` returning `FileResponse`, tile on `static/index.html`, color-scheme meta, `style.css?v=N` / `theme.js?v=N` (current N, unchanged unless `style.css` changes — then bump on every page), top bar, skip link, footer, GoatCounter snippet with `<noscript>` pixel `p=/cron`.
- All parsing/explaining/scheduling/conversion logic lives in `static/cron-logic.js`, a UMD module mirroring `cidr-logic.js` (`window.CronCalc` in the browser, `require()` from Node). `cron.html`'s inline script is DOM wiring only.
- No npm dependencies — the explainer and the next-run calculation are hand-written (no cronstrue, no cron-parser).
- Page `<style>` holds layout only and references tokens; reuse `.card`, `.btn`, `.error`, `.result-list`, `.note`, `.mono`, `.visually-hidden`.
- Mono only for the expression itself, field values and computed times.
- Dynamic regions (explanation, next runs, conversion result, validation error) are `aria-live="polite"`; live validation must not use `role="alert"` on every keystroke. Every control has a visible label. Any animation gets a `prefers-reduced-motion` fallback (none planned).

## Input safety

Nothing typed leaves the browser and nothing is executed, so the threats are DOM injection and inputs that hang the tab. Defences:

- **Length cap:** 512 characters, enforced by `maxlength` on the input *and* in `parse` (paste and programmatic writes bypass `maxlength`). Error: "Expression is too long (max 512 characters)."
- **Character allowlist, not a keyword blocklist:** after trimming, the expression may contain only ASCII `A–Z a–z 0–9`, space, tab, and `* ? , - / # @ ( ) _ =` (the last two only so a `CRON_TZ=…` prefix can be recognised and rejected with a helpful message). Anything else, including non-ASCII digits, zero-width and non-breaking spaces, `<`, `>`, quotes, `;`, `$`, backticks and newlines inside the expression, is rejected: "Unsupported character "X" at position N." The offending character is echoed as plain text and replaced by its `U+XXXX` code when invisible or non-printable. Field splitting uses `/[ \t]+/`, not `\s` (which matches Unicode whitespace).
- **Bounded work:** step `0` is an error ("step must be at least 1"); numbers longer than 4 digits are rejected before conversion to a number; at most 7 fields and 64 comma-separated items per field; `nextRuns` is bounded by its 5-year day window. The parser tokenises with anchored, non-nested regexes (no backtracking blow-up) or plain string splitting.
- **Safe rendering:** every user-derived string reaches the DOM through `textContent`, `value` or `createElement`; `cron.html` and `cron-logic.js` contain no `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `new Function` or string `setTimeout`. A pytest guards this.
- **Echo length:** error messages quote at most 20 characters of a user token (truncated with "…").
- **Builder inputs** are number inputs with `min`/`max` plus the same `parse` validation; the *Custom* raw field goes through the same allowlist and length check.
- **No URL state:** expressions are never written to the URL, so they don't reach logs or analytics (already a non-goal).

Out of scope here: a Content-Security-Policy header. It would be a site-wide nginx change, and the existing pages use inline scripts, so it deserves its own task.

## Flavour rules

The builder must verify each row against the official docs while implementing; rows marked ⚠ are ones I'm least sure of.

| Flavour | Fields | Day-of-week | `?` | `L` `W` `#` | Macros | Notes |
|---|---|---|---|---|---|---|
| Unix | min hour dom mon dow | 0–7 (0 and 7 = Sun), SUN–SAT | no | no | `@yearly @annually @monthly @weekly @daily @midnight @hourly @reboot` | dom+dow both restricted ⇒ **OR** |
| Kubernetes | min hour dom mon dow | 0–6, SUN–SAT ⚠ | accepted as `*` ⚠ | no | as Unix minus `@reboot` | `CRON_TZ=`/`TZ=` prefix rejected with a pointer to `spec.timeZone`; OR semantics |
| GitHub Actions | min hour dom mon dow | 0–6, SUN–SAT | no | no | none | always UTC; schedules more often than every 5 min get a warning; OR semantics |
| Quartz | sec min hour dom mon dow [year] | 1–7 (1 = Sun), SUN–SAT | exactly one of dom/dow must be `?` | yes | none | year 1970–2099 |
| AWS EventBridge | min hour dom mon dow year | 1–7 (1 = Sun), SUN–SAT | exactly one of dom/dow must be `?` | yes | none | year 1970–2199; input accepted with or without `cron(...)` wrapper |
| Spring | sec min hour dom mon dow | 0–7 (0 and 7 = Sun), SUN–SAT | accepted as `*` | yes | as Unix minus `@reboot` | dom+dow semantics ⚠ — verify (AND vs OR) against `CronExpression` |

`@reboot` is valid Unix but has no schedule: explained as "At system startup", no next runs, not convertible.

## Logic module (`cron-logic.js`)

Rough API (names are the builder's call):

- `parse(expr, flavour)` → normalized structure (per field: set of allowed values plus the original special tokens like `L`, `15W`, `6#3`) or `{ error, field }`.
- `explain(parsed)` → English sentence, e.g. `0 9 * * 1-5` → "At 09:00, Monday through Friday." Times as 24-hour `HH:MM` (or `HH:MM:SS` when seconds aren't 0).
- `nextRuns(parsed, fromDate, n = 5)` → UTC `Date`s. Iterates in UTC only. Bounded search (e.g. ~5 years ahead); an expression that never fires (`0 0 30 2 *`) yields an empty list, shown as "This expression never runs."
- `toFields(parsed)` / `fromFields(fields, flavour)` for the builder.
- `convert(expr, from, to)` → `{ expression, warnings[] }` or `{ error }`.

### Conversion policy

The rule is **same run set ⇒ convert silently; run time shifted but days unchanged ⇒ convert with a warning; different run set ⇒ refuse with the reason.**

| Situation | Result |
|---|---|
| Day-of-week numbering differs (0–7 Sun=0 ↔ 1–7 Sun=1) | renumber; names stay names |
| Target needs `?` and source has dom or dow as `*` | insert `?` in the unrestricted one |
| Source has dom and dow both restricted (OR) → Quartz/AWS | **refuse**: "Quartz can't express 'day X or weekday Y' in one expression; split it into two schedules" (showing both is a nice-to-have) |
| Source `?` → target without `?` | becomes `*` |
| Single fixed seconds value ≠ 0 → minute-based target | convert, drop seconds, **warn** "will run at :00 instead of :SS" |
| Seconds field with list/step/range (sub-minute runs) → minute-based target | **refuse** |
| Minute-based → seconds target | add `0` seconds |
| Specific year (not `*`) → target without year field | **refuse** |
| → AWS | add year `*`; output wrapped as `cron(...)` |
| `L`, `W`, `#`, `LW`, `L-n` → Unix/Kubernetes/GitHub | **refuse**, naming the token |
| Macro → target without macros | expand (`@daily` → `0 0 * * *`, plus seconds/`?`/year as needed) |
| `a/n` start-step → Unix-family | rewrite as `a-max/n` |
| Result is more frequent than every 5 min and target is GitHub | convert, **warn** about the 5-minute minimum |
| Target same as source | output unchanged |

## Page (`cron.html`)

Top to bottom, inside `<main>` (layout is my call; details are the builder's):

1. `h1` "Cron expression calculator" + `.description`.
2. **Card: expression.** Flavour `<select>` (label "Flavour") and expression text input (label "Cron expression", mono, placeholder showing that flavour's field order). Below it a field-order hint (e.g. `minute hour day-of-month month day-of-week`) that changes with the flavour. Validation error in an `aria-live` region, naming the field ("Field 3 (day of month): 32 is out of range 1–31").
3. **Result** in the same card: explanation sentence; "Next 5 runs" list in mono; `.note` "All times are UTC." Hidden until valid.
4. **Card: builder.** One `<fieldset>` per field with a `<legend>`. Each has a mode `<select>`: *Every*, *Every N (starting at …)*, *Specific values*, *Range*, and only where the flavour allows: *No specific value (`?`)*, *Last day / Last weekday-of-month (`L`)*, *Nearest weekday (`W`)*, *Nth weekday (`#`)*. Inputs for the chosen mode appear beside it. A field value the modes can't represent (e.g. `1-5,10-20/2`) shows a *Custom* mode with a raw text input. Builder edits rewrite the expression input, and typing in the expression input repopulates the builder. Changing flavour rebuilds the field set. If the current expression is valid in the new flavour it stays. If not, it's converted when possible, with the conversion's warnings shown; otherwise the error is shown.
5. **Card: convert.** Target flavour `<select>`, "Convert" button (or live, builder's call), result expression in mono with a "Copy" button (`.btn-secondary`; announce "Copied" via the live region), warnings as a list, refusals in `.error`.

GitHub Actions selected ⇒ the UTC note is reinforced ("GitHub Actions always runs schedules in UTC"); same for AWS EventBridge rules.

## Tests

- `tests/cron_logic.test.js` (picked up by `node --test`): parse/validate per flavour (valid and invalid cases, error names the field), explain for common shapes, nextRuns from a fixed `Date` (including OR semantics, `L`, `W`, `#`, leap years, never-runs), every row of the conversion policy table, builder round-trip.
- `tests/test_routes.py`: `/cron` serves HTML.
- `tests/test_theme.py`: add `/cron` to the themed-routes parametrize; add a `test_cron_keeps_script_hooks_and_labels` mirroring the CIDR one (`<script src="/cron-logic.js"></script>`, labelled inputs).
- `tests/test_analytics.py`: add `"cron.html": "/cron"` to `PAGES` (the test fails otherwise).

## Docs

- README: "Cron Calculator" section next to "CIDR Calculator", the tests line, and the file tree.
- DESIGN.md mono list: add cron expressions / run times.

## Calls I made (for review)

- Flavour list and the rules table above (⚠ rows to be verified).
- The conversion policy, especially: dropping a single seconds value is a warning, not a refusal.
- AWS output is wrapped in `cron(...)`.
- Builder mode-select design with a *Custom* fallback.
- Page section order: expression → result → builder → convert.
- 5 next runs, 24-hour times, English only (like the other tool pages).
- No shareable URLs, no presets, no time zones in v1.
