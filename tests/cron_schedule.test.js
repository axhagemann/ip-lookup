const test = require("node:test");
const assert = require("node:assert/strict");
const { parse, nextRuns } = require("../static/cron-logic.js");

const iso = (e, fl, from, n) => nextRuns(parse(e, fl).cron, new Date(from), n).map((d) => d.toISOString());

test("weekdays at 09:00", () =>
  assert.deepEqual(iso("0 9 * * 1-5", "unix", "2026-11-06T10:00:00Z", 3), [
    "2026-11-09T09:00:00.000Z",
    "2026-11-10T09:00:00.000Z",
    "2026-11-11T09:00:00.000Z",
  ]));
test("strictly after from", () =>
  assert.deepEqual(iso("0 9 * * *", "unix", "2026-11-06T09:00:00Z", 1), ["2026-11-07T09:00:00.000Z"]));
test("seconds", () =>
  assert.deepEqual(iso("30 0 12 * * ?", "quartz", "2026-11-01T00:00:00Z", 1), ["2026-11-01T12:00:30.000Z"]));
test("vixie OR when both restricted", () =>
  assert.deepEqual(iso("0 0 1 * 1", "unix", "2026-11-01T00:00:00Z", 3), [
    "2026-11-02T00:00:00.000Z",
    "2026-11-09T00:00:00.000Z",
    "2026-11-16T00:00:00.000Z",
  ]));
test("vixie OR includes the dom match", () =>
  assert.deepEqual(iso("0 0 1 * 1", "unix", "2026-11-28T00:00:00Z", 3), [
    "2026-11-30T00:00:00.000Z",
    "2026-12-01T00:00:00.000Z",
    "2026-12-07T00:00:00.000Z",
  ]));
test("vixie star-step dom means AND", () =>
  assert.deepEqual(iso("0 0 */2 * 1", "unix", "2026-11-01T00:00:00Z", 2), [
    "2026-11-09T00:00:00.000Z",
    "2026-11-23T00:00:00.000Z",
  ]));
test("kubernetes ? in dom means Mondays only", () =>
  assert.deepEqual(iso("0 0 ? * 1", "kubernetes", "2026-11-01T00:00:00Z", 2), [
    "2026-11-02T00:00:00.000Z",
    "2026-11-09T00:00:00.000Z",
  ]));
test("spring AND", () =>
  assert.deepEqual(iso("0 0 0 13 * FRI", "spring", "2026-01-01T00:00:00Z", 1), ["2026-02-13T00:00:00.000Z"]));
test("last day", () =>
  assert.deepEqual(iso("0 0 12 L * ?", "quartz", "2026-02-01T00:00:00Z", 1), ["2026-02-28T12:00:00.000Z"]));
test("L-3", () =>
  assert.deepEqual(iso("0 0 12 L-3 * ?", "quartz", "2026-11-01T00:00:00Z", 1), ["2026-11-27T12:00:00.000Z"]));
test("nearest weekday stays in month", () =>
  assert.deepEqual(iso("0 0 12 1W * ?", "quartz", "2026-11-01T00:00:00Z", 1), ["2026-11-02T12:00:00.000Z"]));
test("nearest weekday moves Saturday 1st to Monday 3rd", () =>
  assert.deepEqual(iso("0 0 12 1W * ?", "quartz", "2026-08-01T00:00:00Z", 1), ["2026-08-03T12:00:00.000Z"]));
test("nearest weekday moves last-day Sunday back to Friday", () =>
  assert.deepEqual(iso("0 0 12 31W * ?", "quartz", "2026-05-01T00:00:00Z", 1), ["2026-05-29T12:00:00.000Z"]));
test("LW", () =>
  assert.deepEqual(iso("0 0 12 LW * ?", "quartz", "2026-01-01T00:00:00Z", 1), ["2026-01-30T12:00:00.000Z"]));
test("nth weekday", () =>
  assert.deepEqual(iso("0 0 10 ? * 6#3", "quartz", "2026-11-01T00:00:00Z", 1), ["2026-11-20T10:00:00.000Z"]));
test("last friday", () =>
  assert.deepEqual(iso("0 0 10 ? * 6L", "quartz", "2026-11-01T00:00:00Z", 1), ["2026-11-27T10:00:00.000Z"]));
test("aws year", () =>
  assert.deepEqual(iso("0 12 1 1 ? 2028", "aws", "2026-11-01T00:00:00Z", 2), ["2028-01-01T12:00:00.000Z"]));
test("@reboot has no runs", () => assert.deepEqual(iso("@reboot", "unix", "2026-11-01T00:00:00Z", 5), []));
test("leap day is found", () =>
  assert.deepEqual(iso("0 0 29 2 *", "unix", "2026-11-01T00:00:00Z", 1), ["2028-02-29T00:00:00.000Z"]));
test("impossible date never runs", () =>
  assert.deepEqual(iso("0 0 31 4 *", "unix", "2026-11-01T00:00:00Z", 5), []));

test("a quartz year beyond the search window finds no runs (page says so without claiming never)", () =>
  assert.deepEqual(iso("0 0 12 * * ? 2035", "quartz", "2026-11-01T00:00:00Z", 5), []));
