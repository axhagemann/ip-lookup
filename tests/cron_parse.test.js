const test = require("node:test");
const assert = require("node:assert/strict");
const { parse, getFlavour, FLAVOURS } = require("../static/cron-logic.js");

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
test("start/step without range is only for quartz, aws, spring, kubernetes", () => {
  assert.deepEqual(parse("5/20 * * * *", "unix"), { ok: false, field: "minute",
    error: "Field 1 (minute): 5/20 isn't supported by Unix cron; use 5-59/20." });
  assert.deepEqual(parse("0 0 * * 1/2", "github"), { ok: false, field: "dow",
    error: "Field 5 (day of week): 1/2 isn't supported by GitHub Actions; use 1-6/2." });
  assert.deepEqual(parse("5/20 * * * *", "kubernetes").cron.fields.minute.values, [5, 25, 45]);
  assert.deepEqual(parse("0 5/30 * * * *", "spring").cron.fields.minute.values, [5, 35]);
  assert.equal(parse("5-59/20 * * * *", "unix").ok, true);
});
test("flavour table", () => {
  assert.deepEqual(FLAVOURS.map((f) => f.id), ["unix", "kubernetes", "github", "quartz", "aws", "spring"]);
  assert.deepEqual(FLAVOURS.map((f) => f.label),
    ["Unix cron", "Kubernetes CronJob", "GitHub Actions", "Quartz", "AWS EventBridge", "Spring"]);
  assert.equal(getFlavour("spring").dayMatch, "and");
  assert.equal(getFlavour("github").minIntervalMinutes, 5);
});
