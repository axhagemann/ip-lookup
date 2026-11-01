const test = require("node:test");
const assert = require("node:assert/strict");
const { parse, nextRuns, toBuilder, fromBuilder, builderModes } = require("../static/cron-logic.js");

test("round trip simple", () => {
  for (const [e, fl] of [
    ["0 9 * * 1-5", "unix"],
    ["*/15 * * * *", "unix"],
    ["0 0 10 ? * 6#3", "quartz"],
    ["0 0 12 L * ?", "quartz"],
    ["0 12 * * ? *", "aws"],
  ])
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

test("macro expands into fields", () =>
  assert.deepEqual(toBuilder(parse("@hourly", "unix").cron).minute, { mode: "specific", values: [0] }));

test("@reboot has no builder", () => assert.equal(toBuilder(parse("@reboot", "unix").cron), null));

test("start/step writes flavour syntax", () => {
  const b = toBuilder(parse("*/5 * * * *", "unix").cron);
  assert.deepEqual(b.minute, { mode: "step", start: 0, step: 5 });
  b.minute = { mode: "step", start: 3, step: 10 };
  assert.equal(fromBuilder(b, "unix"), "3-59/10 * * * *");
  assert.equal(fromBuilder(b, "github"), "3-59/10 * * * *");
  assert.equal(fromBuilder(b, "kubernetes"), "3/10 * * * *");
});

test("builder dow written in flavour numbering", () => {
  const b = toBuilder(parse("0 0 0 ? * *", "quartz").cron);
  b.dow = { mode: "specific", values: [1] }; // Monday
  b.dom = { mode: "none" };
  assert.equal(fromBuilder(b, "quartz"), "0 0 0 ? * 2");
});

test("dow step start is shifted into flavour numbering", () => {
  const b = toBuilder(parse("0 0 0 ? * 2/2", "quartz").cron);
  assert.deepEqual(b.dow, { mode: "step", start: 1, step: 2 });
  assert.equal(fromBuilder(b, "quartz"), "0 0 0 ? * 2/2");
});

test("specials map to last, weekday and nth", () => {
  const q = (e) => toBuilder(parse(e, "quartz").cron);
  assert.deepEqual(q("0 0 0 L-3 * ?").dom, { mode: "last", offset: 3 });
  assert.deepEqual(q("0 0 0 LW * ?").dom, { mode: "weekday", day: "L" });
  assert.deepEqual(q("0 0 0 15W * ?").dom, { mode: "weekday", day: 15 });
  assert.deepEqual(q("0 0 0 ? * 6L").dow, { mode: "last", dow: 5 });
  assert.deepEqual(q("0 0 0 ? * 6#3").dow, { mode: "nth", dow: 5, nth: 3 });
});

test("names become numbers and ? maps per flavour", () => {
  assert.deepEqual(toBuilder(parse("0 0 * JAN,MAR MON,WED", "unix").cron).month, { mode: "specific", values: [1, 3] });
  assert.deepEqual(toBuilder(parse("0 0 * * MON,WED", "unix").cron).dow, { mode: "specific", values: [1, 3] });
  assert.deepEqual(toBuilder(parse("0 0 ? * 1", "kubernetes").cron).dom, { mode: "every" });
  assert.deepEqual(toBuilder(parse("0 0 0 ? * 2", "quartz").cron).dom, { mode: "none" });
});

test("quartz year is omitted when every, written when set", () => {
  const b = toBuilder(parse("0 0 0 ? * 2", "quartz").cron);
  assert.deepEqual(b.year, { mode: "every" });
  b.year = { mode: "specific", values: [2030] };
  assert.equal(fromBuilder(b, "quartz"), "0 0 0 ? * 2 2030");
});

test("empty specific selection is rejected", () => {
  const b = toBuilder(parse("0 9 * * *", "unix").cron);
  b.hour = { mode: "specific", values: [] };
  assert.throws(() => fromBuilder(b, "unix"), /hour/);
});

test("modes offered per flavour", () => {
  assert.deepEqual(builderModes("dom", "github"), ["every", "step", "specific", "range", "custom"]);
  assert.deepEqual(builderModes("dom", "quartz"), ["every", "step", "specific", "range", "none", "last", "weekday", "custom"]);
  assert.deepEqual(builderModes("dow", "aws"), ["every", "step", "specific", "range", "none", "last", "nth", "custom"]);
  assert.deepEqual(builderModes("minute", "quartz"), ["every", "step", "specific", "range", "custom"]);
});

test("fromBuilder output parses and runs identically", () => {
  const from = new Date(Date.UTC(2026, 10, 1));
  const cases = [
    ["0 0 * * 7", "unix"],
    ["0 0 * * 5-7", "unix"],
    ["0 0 * * 0-7", "unix"],
    ["0 0 0 * * 0-7", "spring"],
    ["30 4 1,15 * MON-FRI", "unix"],
    ["*/7 */3 */2 */4 *", "unix"],
    ["@weekly", "unix"],
    ["@yearly", "unix"],
    ["0 0 ? * 1", "kubernetes"],
    ["5/10 1-3 * * *", "kubernetes"],
    ["1-30/5 2 * * 1,3,5", "github"],
    ["0 0 1 1 *", "github"],
    ["0 10/15 * * * ?", "quartz"],
    ["0 0 0 ? * 2/2", "quartz"],
    ["0 0 0 ? * MON,WED", "quartz"],
    ["0 0 0 L-3 * ?", "quartz"],
    ["0 0 0 LW * ?", "quartz"],
    ["0 0 0 15W * ?", "quartz"],
    ["0 0 0 ? * 6L", "quartz"],
    ["0 0 0 ? * 6#3 2030", "quartz"],
    ["0 0 0 ? 2/3 *", "quartz"],
    ["0 12 * * ? 2027-2029", "aws"],
    ["0/5 8-17 ? * MON-FRI *", "aws"],
    ["0 0 */2 * * ?", "spring"],
    ["0 0 0 L * 1", "spring"],
    ["0 0 0 ? * MON-FRI", "spring"],
    ["0 0 0 1-15/2 * *", "spring"],
  ];
  for (const [e, fl] of cases) {
    const cron = parse(e, fl).cron;
    const out = fromBuilder(toBuilder(cron), fl);
    const back = parse(out, fl);
    assert.equal(back.ok, true, `${e} -> ${out}: ${back.error}`);
    const times = (c) => nextRuns(c, from, 20).map((d) => d.getTime());
    assert.deepEqual(times(back.cron), times(cron), `${e} -> ${out}`);
  }
});

test("spring dow steps become specific values and round-trip with identical runs", () => {
  const from = new Date("2026-11-01T00:00:00Z");
  for (const e of ["0 0 0 * * */2", "0 0 0 * * 1/2", "0 0 0 * * 7/2", "0 0 0 * * 0/3"]) {
    const cron = parse(e, "spring").cron;
    const b = toBuilder(cron);
    assert.equal(b.dow.mode, "specific", e);
    const back = parse(fromBuilder(b, "spring"), "spring");
    assert.equal(back.ok, true);
    assert.deepEqual(nextRuns(back.cron, from, 30), nextRuns(cron, from, 30), e);
  }
});

test("spring dow step mode is written as an explicit list", () => {
  const b = toBuilder(parse("0 0 0 * * *", "spring").cron);
  b.dow = { mode: "step", start: 0, step: 2 };
  assert.match(fromBuilder(b, "spring"), / 0,2,4,6$/);
  b.dow = { mode: "step", start: 1, step: 2 };
  assert.match(fromBuilder(b, "spring"), / 1,3,5$/);
});
