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
    error: "Expected 5 fields (minute hour day-of-month month day-of-week), got 4. Separate the fields with spaces and add the missing ones." });
});
test("out of range names the field", () => {
  assert.deepEqual(parse("0 0 32 * *", "unix"), { ok: false, field: "dom",
    error: "Field 3 (day of month): 32 is too large; use a value from 1 to 31." });
});
test("special not supported by flavour", () => {
  assert.deepEqual(parse("0 0 L * *", "github"), { ok: false, field: "dom",
    error: "Field 3 (day of month): L is not supported by GitHub Actions; L, W and # only work in Quartz, AWS EventBridge and Spring." });
});
test("quartz needs exactly one ?", () => {
  assert.equal(parse("0 0 12 * * *", "quartz").error, "Quartz needs ? in exactly one of day of month and day of week. Try 0 0 12 * * ? instead.");
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
    error: "Field 5 (day of week): range 5-1 starts after it ends; write it as 1-5." });
  assert.equal(parse("0 0 * * FRI-MON", "unix").ok, false);
});
// Input safety
test("length cap", () => {
  assert.deepEqual(parse("0 ".repeat(300), "unix"), { ok: false, field: null,
    error: "Expression is too long (max 512 characters)." });
});
test("character allowlist", () => {
  assert.deepEqual(parse("0 9 * * <script>", "unix"), { ok: false, field: null,
    error: 'Unsupported character "<" at position 9; remove it.' });
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
    error: "Field 1 (minute): step must be at least 1, e.g. */5." });
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

// Every error says what to do next.
const err = (e, fl) => parse(e, fl).error;
test("field count hints name the likely fix", () => {
  assert.equal(err("0 12 * * ?", "aws"),
    "Expected 6 fields (minute hour day-of-month month day-of-week year), got 5. Add a year at the end, e.g. *.");
  assert.equal(err("0 12 * * ?", "quartz"),
    "Expected 6 or 7 fields (second minute hour day-of-month month day-of-week [year]), got 5. Add a seconds field at the start, e.g. 0.");
  assert.equal(err("0 0 12 * * ?", "unix"),
    "Expected 5 fields (minute hour day-of-month month day-of-week), got 6. If it comes from Quartz, Spring or AWS EventBridge, pick that flavour above.");
  assert.equal(err("0 0 12 * * ? * 1", "quartz"),
    "Expected 6 or 7 fields (second minute hour day-of-month month day-of-week [year]), got 8. Remove the extra fields.");
});
test("? rule suggests a corrected expression", () => {
  assert.equal(err("0 0 12 ? * ?", "quartz"),
    "Quartz needs ? in exactly one of day of month and day of week. Try 0 0 12 * * ? instead.");
  assert.equal(err("0 9 * * 2-6 *", "aws"),
    "AWS EventBridge needs ? in exactly one of day of month and day of week. Try 0 9 ? * 2-6 * instead.");
  assert.equal(err("cron(0 9 1 * 2-6 *)", "aws"),
    "AWS EventBridge needs ? in exactly one of day of month and day of week. Try 0 9 ? * 2-6 * instead.");
  assert.equal(parse(err("0 9 1 * 2-6 *", "aws").match(/Try (.*) instead/)[1], "aws").ok, true);
});
test("value errors say what is allowed", () => {
  assert.equal(err("0 0 0 * *", "unix"), "Field 3 (day of month): 0 is too small; use a value from 1 to 31.");
  assert.equal(err("0 0 * FOO *", "unix"), 'Field 4 (month): invalid value "FOO"; use a number from 1 to 12, a name such as JAN, or *.');
  assert.equal(err("0 0 * * FOO", "unix"), 'Field 5 (day of week): invalid value "FOO"; use a number from 0 to 7, a name such as MON, or *.');
  assert.equal(err("x * * * *", "unix"), 'Field 1 (minute): invalid value "x"; use a number from 0 to 59, or *.');
  assert.equal(err("00000 * * * *", "unix"), "Field 1 (minute): number 00000 is too long; use a value from 0 to 59.");
  assert.equal(err("0 ? * * *", "kubernetes"), "Field 2 (hour): ? is only allowed in day of month and day of week; use * here.");
  assert.equal(err("0 0 ? * *", "unix"), "Field 3 (day of month): ? is not supported by Unix cron; use * instead.");
  assert.equal(err("1,,2 * * * *", "unix"), "Field 1 (minute): empty value in list; remove the extra comma.");
  assert.equal(err("*/x * * * *", "unix"), 'Field 1 (minute): invalid step "x"; the part after / must be a number, e.g. */5.');
  assert.equal(err("0 0 12 L,1 * ?", "quartz"), "Field 4 (day of month): L,1 can't be combined with other values; use it on its own.");
  assert.equal(err("0 0 * * FRI-MON", "unix"), "Field 5 (day of week): range FRI-MON starts after it ends; write it as MON-FRI.");
  assert.match(err(Array(65).fill("1").join(",") + " * * * *", "unix"), /too many values \(max 64\); use a range such as 1-10 instead\.$/);
});
test("macro errors say what to write instead", () => {
  assert.equal(err("@daily 1", "unix"), "A macro can't be combined with other fields; use it on its own, e.g. @daily.");
  assert.equal(err("@nightly", "unix"),
    'Unknown macro "@nightly"; use one of @yearly, @annually, @monthly, @weekly, @daily, @midnight, @hourly or @reboot.');
  assert.equal(err("@daily", "github"), "@daily is not supported by GitHub Actions; write it as 0 0 * * * instead.");
  assert.equal(err("@daily", "quartz"), "@daily is not supported by Quartz; write it as 0 0 0 * * ? instead.");
  assert.equal(err("@nightly", "github"), 'Unknown macro "@nightly"; GitHub Actions has no macros, so write out the fields, e.g. 0 0 * * *.');
  assert.equal(err("@reboot", "kubernetes"), "@reboot is not supported by Kubernetes CronJob; it only runs on a schedule, not at startup.");
  assert.equal(err("TZ=UTC 0 9 * * *", "unix"), "Time zone prefixes aren't supported; remove the TZ=… part. All times here are UTC.");
  assert.equal(err("0 9 * * *;", "unix"), 'Unsupported character ";" at position 10; remove it.');
});
