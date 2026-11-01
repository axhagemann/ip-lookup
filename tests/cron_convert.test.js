const test = require("node:test");
const assert = require("node:assert/strict");
const { convert, parse, nextRuns } = require("../static/cron-logic.js");

const ok = (e, f, t) => {
  const r = convert(e, f, t);
  assert.equal(r.ok, true, r.error);
  return r;
};
const refused = (e, f, t) => {
  const r = convert(e, f, t);
  assert.equal(r.ok, false, e + " should be refused");
  return r.error;
};

// Day-of-week numbering
test("unix → quartz renumbers dow and adds ? and seconds", () =>
  assert.equal(ok("0 9 * * 1-5", "unix", "quartz").expression, "0 0 9 ? * 2-6"));
test("names stay names", () => assert.equal(ok("0 9 * * MON-FRI", "unix", "quartz").expression, "0 0 9 ? * MON-FRI"));
test("unix 7 converts to quartz 1", () => assert.equal(ok("0 0 * * 7", "unix", "quartz").expression, "0 0 0 ? * 1"));
test("dow step becomes explicit list", () =>
  assert.equal(ok("0 0 * * */2", "unix", "quartz").expression, "0 0 0 ? * 1,3,5,7"));
test("dow range ending in 7 becomes an explicit list", () =>
  assert.equal(ok("0 0 * * 5-7", "unix", "quartz").expression, "0 0 0 ? * 1,6,7"));
test("dow 0-7 covers every day", () =>
  assert.equal(ok("0 0 * * 0-7", "unix", "quartz").expression, "0 0 0 ? * 1,2,3,4,5,6,7"));
test("quartz dow shifts down for unix", () => assert.equal(ok("0 0 12 ? * 2-6", "quartz", "unix").expression, "0 12 * * 1-5"));
test("unix 7 becomes 0 for kubernetes", () => assert.equal(ok("0 0 * * 7", "unix", "kubernetes").expression, "0 0 * * 0"));
test("unix 5-7 becomes explicit list for kubernetes", () =>
  assert.equal(ok("0 0 * * 5-7", "unix", "kubernetes").expression, "0 0 * * 0,5,6"));
test("unix 5-7 stays for spring (same numbering)", () =>
  assert.equal(ok("0 0 * * 5-7", "unix", "spring").expression, "0 0 0 * * 5-7"));
test("dow specials are renumbered, names kept", () => {
  assert.equal(ok("0 0 12 ? * 6#3", "quartz", "spring").expression, "0 0 12 * * 5#3");
  assert.equal(ok("0 0 12 ? * FRIL", "quartz", "spring").expression, "0 0 12 * * FRIL");
  assert.equal(ok("0 0 0 * * 5L", "spring", "quartz").expression, "0 0 0 ? * 6L");
});

// ? handling
test("dom restricted gets ? in dow", () => assert.equal(ok("0 0 1 * *", "unix", "aws").expression, "cron(0 0 1 * ? *)"));
test("both unrestricted: ? goes in dow", () =>
  assert.equal(ok("0 12 * * *", "unix", "quartz").expression, "0 0 12 * * ?"));
test("? becomes * for unix", () => assert.equal(ok("0 0 12 ? * MON", "quartz", "unix").expression, "0 12 * * MON"));
test("? becomes * for kubernetes and spring", () => {
  assert.equal(ok("0 0 12 1 * ?", "quartz", "kubernetes").expression, "0 12 1 * *");
  assert.equal(ok("0 0 12 ? * MON", "quartz", "spring").expression, "0 0 12 * * MON");
});

// Day semantics
test("both restricted (OR) refuses for quartz/aws", () => {
  assert.match(refused("0 0 1 * 1", "unix", "quartz"), /split it into two schedules/);
  assert.match(refused("0 0 1 * 1", "unix", "aws"), /split it into two schedules/);
});
test("OR → spring refuses (spring requires both)", () =>
  assert.match(refused("0 0 1 * 1", "unix", "spring"), /split it into two schedules/));
test("OR between OR flavours converts", () => {
  assert.equal(ok("0 0 1 * 1", "unix", "github").expression, "0 0 1 * 1");
  assert.equal(ok("0 0 1 * 1", "unix", "kubernetes").expression, "0 0 1 * 1");
});
test("star trap: unix */2 with a weekday is AND, so spring accepts it", () =>
  assert.equal(ok("0 0 */2 * 1", "unix", "spring").expression, "0 0 0 */2 * 1"));
test("star trap: unix 1-31/2 with a weekday is OR, so spring refuses", () =>
  refused("0 0 1-31/2 * 1", "unix", "spring"));
test("spring AND with */2 and a weekday → unix keeps AND", () =>
  assert.equal(ok("0 0 0 */2 * MON", "spring", "unix").expression, "0 0 */2 * MON"));
test("spring AND with both restricted refuses for OR and single flavours", () => {
  refused("0 0 0 1-15 * MON", "spring", "unix");
  refused("0 0 0 1-15 * MON", "spring", "quartz");
});
test("AND with a stepped star day can't use ? so quartz refuses", () =>
  refused("0 0 */2 * 1", "unix", "quartz"));
test("dow */n keeps its star when renumbering for 7 (AND must stay AND)", () => {
  assert.equal(ok("0 0 1 * */2", "unix", "github").expression, "0 0 1 * */2");
  refused("0 0 1 * */2", "unix", "quartz");
  // Kubernetes follows robfig/cron (*/n is not a star there) and Spring steps from Monday: both refuse.
  refused("0 0 1 * */2", "unix", "kubernetes");
  refused("0 0 0 1 * */2", "spring", "kubernetes");
  refused("0 0 0 1 * */2", "spring", "github");
});
test("spring with open dom → quartz", () =>
  assert.equal(ok("0 0 8 * * MON", "spring", "quartz").expression, "0 0 8 ? * MON"));

// Seconds
test("fixed seconds dropped with warning", () => {
  const r = ok("30 0 12 * * ?", "quartz", "unix");
  assert.equal(r.expression, "0 12 * * *");
  assert.deepEqual(r.warnings, ["Unix cron has no seconds field, so this will run at :00 instead of :30."]);
});
test("zero seconds dropped silently", () => assert.deepEqual(ok("0 0 12 * * ?", "quartz", "unix").warnings, []));
test("sub-minute seconds refuse", () => {
  refused("*/10 * * * * ?", "quartz", "unix");
  refused("0,30 * * * * ?", "quartz", "aws");
});
test("minute-based → seconds target adds 0", () => {
  assert.equal(ok("5 4 * * *", "unix", "spring").expression, "0 5 4 * * *");
  assert.equal(ok("0 0 12 * * ?", "quartz", "spring").expression, "0 0 12 * * *");
});

// Year
test("specific year refuses for yearless target", () => refused("0 12 1 1 ? 2028", "aws", "unix"));
test("star year dropped silently", () => assert.deepEqual(ok("0 12 * * ? *", "aws", "github").warnings, []));
test("star year omitted for quartz, added for aws", () => {
  assert.equal(ok("0 12 * * ? *", "aws", "quartz").expression, "0 0 12 * * ?");
  assert.equal(ok("0 0 12 * * ?", "quartz", "aws").expression, "cron(0 12 * * ? *)");
});
test("specific year is kept between year flavours", () => {
  assert.equal(ok("0 12 1 1 ? 2028", "aws", "quartz").expression, "0 0 12 1 1 ? 2028");
  assert.equal(ok("0 0 12 1 1 ? 2028", "quartz", "aws").expression, "cron(0 12 1 1 ? 2028)");
});
test("year outside the target range refuses", () => refused("0 12 1 1 ? 2150", "aws", "quartz"));

// Specials, macros
test("L to unix refuses naming token", () => assert.match(refused("0 0 12 L * ?", "quartz", "unix"), /\bL\b/));
test("5#2 refuses for github naming token", () => assert.match(refused("0 0 12 ? * 2#2", "quartz", "github"), /2#2/));
test("specials survive between special flavours", () =>
  assert.equal(ok("0 0 12 L * ?", "quartz", "aws").expression, "cron(0 12 L * ? *)"));
test("macro expands when target has none", () => assert.equal(ok("@daily", "unix", "quartz").expression, "0 0 0 * * ?"));
test("macro expands for aws and github", () => {
  assert.equal(ok("@hourly", "unix", "aws").expression, "cron(0 * * * ? *)");
  assert.equal(ok("@weekly", "unix", "github").expression, "0 0 * * 0");
});
test("macro kept when target supports it", () => {
  assert.equal(ok("@daily", "unix", "kubernetes").expression, "@daily");
  assert.equal(ok("@daily", "spring", "unix").expression, "@daily");
});
test("@reboot refuses", () => {
  refused("@reboot", "unix", "kubernetes");
  refused("@reboot", "unix", "quartz");
});

// Start/step
test("start/step rewritten for unix family", () => {
  assert.equal(ok("0 5/20 * * * ?", "quartz", "unix").expression, "5-59/20 * * * *");
  assert.equal(ok("0 0 0 1/2 * ?", "quartz", "github").expression, "0 0 1-31/2 * *");
  assert.equal(ok("0 5/20 * * * *", "spring", "kubernetes").expression, "5-59/20 * * * *");
  assert.equal(ok("0 0 0 * * 1/2", "spring", "unix").expression, "0 0 * * 0,1,3,5");
});
test("start/step kept where supported", () =>
  assert.equal(ok("0 5/20 * * * ?", "quartz", "aws").expression, "cron(5/20 * * * ? *)"));

// GitHub minimum interval
test("github 5-minute warning", () => {
  assert.equal(ok("*/2 * * * *", "unix", "github").warnings.length, 1);
  assert.deepEqual(ok("*/5 * * * *", "unix", "github").warnings, []);
  assert.match(ok("*/2 * * * *", "unix", "github").warnings[0], /every 5 minutes/);
});
test("github warns for close minutes in a list, and for wrap-around", () => {
  assert.equal(ok("0,3 * * * *", "unix", "github").warnings.length, 1);
  assert.equal(ok("0,58 * * * *", "unix", "github").warnings.length, 1);
  assert.deepEqual(ok("0,58 12 * * *", "unix", "github").warnings, []);
  assert.deepEqual(ok("0 * * * *", "unix", "github").warnings, []);
});
test("no github warning for other targets", () => assert.deepEqual(ok("* * * * *", "unix", "quartz").warnings, []));

// Misc
test("same flavour unchanged", () => assert.equal(ok("0 9 * * 1-5", "unix", "unix").expression, "0 9 * * 1-5"));
test("invalid source returns parse error", () => assert.equal(convert("0 0 32 * *", "unix", "quartz").ok, false));
test("aws cron() wrapper accepted as source", () =>
  assert.equal(ok("cron(0 12 * * ? *)", "aws", "unix").expression, "0 12 * * *"));

// Round-trip behavioural check: source and target produce the same run times.
const PAIRS = [
  ["0 9 * * 1-5", "unix", "quartz"],
  ["0 9 * * MON-FRI", "unix", "aws"],
  ["0 0 * * 5-7", "unix", "quartz"],
  ["0 0 * * 5-7", "unix", "kubernetes"],
  ["0 0 * * 0-7", "unix", "aws"],
  ["0 0 * * */2", "unix", "quartz"],
  ["0 0 1 * *", "unix", "aws"],
  ["0 0 */2 * 1", "unix", "spring"],
  ["0 0 1 * 1", "unix", "github"],
  ["0 0 0 */2 * MON", "spring", "unix"],
  ["0 0 8 * * MON", "spring", "quartz"],
  ["0 0 12 ? * 6#3", "quartz", "spring"],
  ["0 0 12 L * ?", "quartz", "aws"],
  ["0 15 10 ? * 2-6", "quartz", "unix"],
  ["0 5/20 * * * ?", "quartz", "unix"],
  ["0 12 1 1 ? 2028", "aws", "quartz"],
  ["@weekly", "unix", "quartz"],
  ["@monthly", "unix", "aws"],
  ["0 0 1 * */2", "unix", "github"],
  ["30 4 29 2 *", "unix", "spring"],
];
for (const [expr, from, to] of PAIRS) {
  test(`same runs: ${expr} ${from} → ${to}`, () => {
    const out = ok(expr, from, to).expression;
    const at = new Date("2026-11-01T00:00:00Z");
    const a = nextRuns(parse(expr, from).cron, at, 12).map((d) => d.toISOString());
    const b = nextRuns(parse(out, to).cron, at, 12).map((d) => d.toISOString());
    assert.ok(a.length > 0);
    assert.deepEqual(b, a, out);
  });
}

// ---- R18: switchFlavour ---------------------------------------------------
const { switchFlavour, explain } = require("../static/cron-logic.js");

test("switchFlavour: blank input is empty", () => {
  assert.deepEqual(switchFlavour("   ", "unix", "quartz"), { action: "empty" });
});
test("switchFlavour: pasted quartz text under unix is reparsed, not converted", () =>
  assert.deepEqual(switchFlavour("0 0 12 * * ?", "unix", "quartz"), { action: "reparse" }));
test("switchFlavour: valid text converts", () => {
  const r = switchFlavour("0 9 * * 1-5", "unix", "quartz");
  assert.equal(r.action, "converted");
  assert.equal(r.expression, "0 0 9 ? * 2-6");
  assert.deepEqual(r.warnings, []);
});
test("switchFlavour: valid but unconvertible text is refused with the reason", () => {
  const r = switchFlavour("0 0 1 * 1", "unix", "quartz");
  assert.equal(r.action, "refused");
  assert.ok(r.error.length > 10);
});

// ---- R19: star rule (Kubernetes follows robfig/cron, Unix follows Vixie) ----
const T0 = new Date("2026-11-01T00:00:00Z");
const runs = (e, f, n = 60) => nextRuns(parse(e, f).cron, T0, n).map((d) => d.toISOString());

test("kubernetes: */2 day-of-month with a weekday is OR, unix is AND", () => {
  const k = runs("0 0 */2 * 1", "kubernetes");
  const u = runs("0 0 */2 * 1", "unix");
  assert.notDeepEqual(k, u);
  // Nov 3 is a Tuesday and an odd day: it matches the day-of-month side only.
  assert.ok(k.includes("2026-11-03T00:00:00.000Z"));
  assert.ok(!u.includes("2026-11-03T00:00:00.000Z"));
});
test("kubernetes: */1 is still open (AND)", () => {
  assert.deepEqual(runs("0 0 */1 * 1", "kubernetes"), runs("0 0 * * 1", "kubernetes"));
});
test("explain: kubernetes */2 with weekday says or", () => {
  assert.match(explain(parse("0 0 */2 * 1", "kubernetes").cron), / or /);
  assert.doesNotMatch(explain(parse("0 0 */2 * 1", "unix").cron), / or /);
});
test("unix → kubernetes refuses AND that depends on a */n field", () => {
  refused("0 0 */2 * 1", "unix", "kubernetes");
  refused("0 0 1 * */2", "unix", "kubernetes");
});
test("unix → kubernetes with the other day field open is fine", () => {
  assert.equal(ok("0 0 */2 * *", "unix", "kubernetes").expression, "0 0 */2 * *");
});
test("kubernetes → unix/github rewrites */n so the OR stays an OR", () => {
  for (const t of ["unix", "github"]) {
    const r = ok("0 0 */2 * 1", "kubernetes", t);
    assert.equal(r.expression, "0 0 1-31/2 * 1");
    assert.deepEqual(runs(r.expression, t), runs("0 0 */2 * 1", "kubernetes"));
  }
  const d = ok("0 0 1 * */2", "kubernetes", "unix");
  assert.equal(d.expression, "0 0 1 * 0-6/2");
  assert.deepEqual(runs(d.expression, "unix"), runs("0 0 1 * */2", "kubernetes"));
});
test("unix 1-31/n OR → kubernetes works unchanged", () => {
  const r = ok("0 0 1-31/2 * 1", "unix", "kubernetes");
  assert.equal(r.expression, "0 0 1-31/2 * 1");
  assert.deepEqual(runs(r.expression, "kubernetes"), runs("0 0 1-31/2 * 1", "unix"));
});
test("vixie: lists starting with a number are OR, starting with * are AND", () => {
  const orSet = runs("0 0 1,15 * 1", "unix");
  const andSet = runs("0 0 */5 * 1", "unix");
  assert.ok(orSet.includes("2026-11-02T00:00:00.000Z") && orSet.includes("2026-11-15T00:00:00.000Z"));
  assert.ok(!andSet.includes("2026-11-02T00:00:00.000Z")); // Monday, but day 2 is not in */5 (1,6,..)
});
test("kubernetes mixed list */2,5 is not open", () => {
  assert.ok(runs("0 0 */2,5 * 1", "kubernetes").includes("2026-11-02T00:00:00.000Z"));
});

// ---- R20: Spring day-of-week steps are Monday-based ----------------------
const dows = (e, f) => [...new Set(runs(e, f, 14).map((s) => new Date(s).getUTCDay()))].sort();
test("spring dow */2 is Mon Wed Fri Sun", () => assert.deepEqual(dows("0 0 0 * * */2", "spring"), [0, 1, 3, 5]));
test("spring dow 1/2 is Mon Wed Fri Sun", () => assert.deepEqual(dows("0 0 0 * * 1/2", "spring"), [0, 1, 3, 5]));
test("spring dow 7/2 is Sunday", () => assert.deepEqual(dows("0 0 0 * * 7/2", "spring"), [0]));
test("spring dow 0/2 is Sun Tue Thu Sat", () => assert.deepEqual(dows("0 0 0 * * 0/2", "spring"), [0, 2, 4, 6]));
test("explain never emits an empty day list", () => {
  const s = explain(parse("0 0 0 * * 7/2", "spring").cron);
  assert.doesNotMatch(s, /on \.|on ,|on$/);
  assert.match(s, /Sunday/);
  const c = parse("0 0 0 * * 1", "spring").cron;
  c.fields.dow.values = [];
  assert.doesNotMatch(explain(c), /on \./);
});
test("unix → spring and back expands dow steps explicitly", () => {
  const a = ok("0 0 * * */2", "unix", "spring");
  assert.equal(a.expression, "0 0 0 * * 0,2,4,6");
  assert.deepEqual(runs(a.expression, "spring"), runs("0 0 * * */2", "unix"));
  const b = ok("0 0 0 * * */2", "spring", "unix");
  assert.equal(b.expression, "0 0 * * 0,1,3,5");
  assert.deepEqual(runs(b.expression, "unix"), runs("0 0 0 * * */2", "spring"));
  const c = ok("0 0 0 * * 1/2", "spring", "quartz");
  assert.deepEqual(runs(c.expression, "quartz"), runs("0 0 0 * * 1/2", "spring"));
});

// ---- Regression net: silent conversions must keep the run set -------------
const IDS = ["unix", "kubernetes", "github", "quartz", "aws", "spring"];
const CORPUS = {
  unix: [
    "0 0 * * *", "*/15 * * * *", "0 9 * * 1-5", "0 0 * * 7", "0 0 * * 5-7", "0 0 1 * 1", "0 0 */2 * 1",
    "0 0 1 * */2", "0 0 1-31/2 * 1", "0 0 1,15 * 1,3", "0 0 *,15 * 1", "0 0 1 */3 *", "30 6 29 2 *",
    "0 0 * * */2", "0 12 1-7 * MON", "0 0 15 JAN-MAR *", "@daily", "@weekly", "@monthly", "0 0 31 * *",
    "0 0 */3 * *", "5,35 */6 * * 0", "0 0 * * 0-6/3",
  ],
  kubernetes: ["0 0 */2 * 1", "0 0 1 * */2", "0 0 */1 * 1", "0 0 */2,5 * 1", "0 0 ? * 1", "0 0 */2 * *", "0 0 * * 0", "@hourly", "0 0 1-31/2 * 1"],
  github: ["0 0 * * 1", "*/5 * * * *", "30 5,17 * * 1-5", "0 0 */2 * 1", "0 0 1 * 0-6/2"],
  quartz: ["0 0 12 * * ?", "0 15 10 ? * MON-FRI", "0 0 12 ? * 1", "0 0 12 1 * ?", "0 0/5 * * * ?", "0 0 12 L * ?", "0 0 12 ? * 6L", "0 0 12 ? * 2#1", "0 0 12 * * ? 2027", "0 0 12 15W * ?"],
  aws: ["0 12 * * ? *", "0 12 ? * 2-6 *", "0 12 1 * ? *", "0 12 L * ? 2027", "30 8 ? * 1 *"],
  spring: ["0 0 0 * * *", "0 0 0 * * */2", "0 0 0 * * 1/2", "0 0 0 * * 7/2", "0 0 0 * * 0/2", "0 0 0 1 * *", "0 0 0 * * MON-FRI", "0 0 0 5 * 1", "0 0 0 5 * */2", "0 0 0 * * 5-7", "0 0 8 1 * ?", "0 0 0 * * 0", "0 0 0 L * *", "0 0 0 * * 5L", "@daily"],
};
for (const src of IDS) {
  for (const expr of CORPUS[src]) {
    for (const tgt of IDS) {
      if (tgt === src) continue;
      test(`net: ${src} "${expr}" → ${tgt}`, () => {
        const p = parse(expr, src);
        assert.equal(p.ok, true, expr + ": " + p.error);
        const r = convert(expr, src, tgt);
        if (!r.ok || r.warnings.length) return;
        const q = parse(r.expression, tgt);
        assert.equal(q.ok, true, r.expression);
        const a = nextRuns(p.cron, T0, 60).map((d) => d.toISOString());
        const b = nextRuns(q.cron, T0, 60).map((d) => d.toISOString());
        assert.deepEqual(b, a, `${expr} → ${r.expression}`);
      });
    }
  }
}
