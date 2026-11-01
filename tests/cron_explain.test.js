const test = require("node:test");
const assert = require("node:assert/strict");
const { parse, explain } = require("../static/cron-logic.js");

const say = (e, fl) => {
  const r = parse(e, fl);
  assert.ok(r.ok, e + ": " + r.error);
  return explain(r.cron);
};

const TABLE = [
  ["* * * * *", "unix", "Every minute."],
  ["*/15 * * * *", "unix", "Every 15 minutes."],
  ["0 * * * *", "unix", "At minute 0 of every hour."],
  ["0 */2 * * *", "unix", "At minute 0 past every 2nd hour."],
  ["0 9 * * 1-5", "unix", "At 09:00, Monday through Friday."],
  ["30 2 1 * *", "unix", "At 02:30, on day 1 of the month."],
  ["0 0 * * 0", "unix", "At 00:00, on Sunday."],
  ["0 12 * 1,6 *", "unix", "At 12:00, in January and June."],
  ["0 0 1 * 1", "unix", "At 00:00, on day 1 of the month or on Monday."],
  ["0 0 0 13 * FRI", "spring", "At 00:00, on day 13 of the month if it falls on a Friday."],
  ["30 0 12 * * ?", "quartz", "At 12:00:30."],
  ["0 0 12 L * ?", "quartz", "At 12:00, on the last day of the month."],
  ["0 0 12 L-3 * ?", "quartz", "At 12:00, 3 days before the last day of the month."],
  ["0 0 12 15W * ?", "quartz", "At 12:00, on the weekday nearest day 15 of the month."],
  ["0 0 12 LW * ?", "quartz", "At 12:00, on the last weekday of the month."],
  ["0 0 10 ? * 6#3", "quartz", "At 10:00, on the third Friday of the month."],
  ["0 0 10 ? * 6L", "quartz", "At 10:00, on the last Friday of the month."],
  ["0 12 * * ? 2027", "aws", "At 12:00, in 2027."],
  ["0 9,17 * * *", "unix", "At 09:00 and 17:00."],
  ["@reboot", "unix", "At system startup."],
];

for (const [expr, flavour, expected] of TABLE) {
  test(`${flavour}: ${expr}`, () => assert.equal(say(expr, flavour), expected));
}

const EXTRA = [
  ["5-10 * * * *", "unix", "At minutes 5 through 10 of every hour."],
  ["*/5 9-17 * * *", "unix", "Every 5 minutes during hours 9 through 17."],
  ["0 8-18/2 * * *", "unix", "At minute 0 past every 2nd hour from hour 8 through 18."],
  ["0 0 1,15 * *", "unix", "At 00:00, on days 1 and 15 of the month."],
  ["0 0 1 3-5 *", "unix", "At 00:00, on day 1 of the month, in March through May."],
  ["0 0 * * 7", "unix", "At 00:00, on Sunday."],
  ["0 0 * * MON,WED", "unix", "At 00:00, on Monday and Wednesday."],
  ["0 0 ? * 1", "kubernetes", "At 00:00, on Monday."],
  ["0 0 */3 * *", "unix", "At 00:00, on every 3rd day of the month."],
  ["0 0 1 */3 *", "unix", "At 00:00, on day 1 of the month, in every 3rd month."],
  ["*/10 * * * * *", "spring", "Every 10 seconds."],
  ["30 * * * * *", "spring", "At second 30 of every minute."],
  ["0 0 12 ? * 2-6", "quartz", "At 12:00, Monday through Friday."],
  ["0 12 * * ? 2027-2030", "aws", "At 12:00, in 2027 through 2030."],
  // Steps that don't divide the range, partial ranges, and month+year phrasing.
  ["*/7 * * * *", "unix", "At every 7th minute."],
  ["* */7 * * *", "unix", "Every minute during every 7th hour."],
  ["0 0 */2 * *", "unix", "At 00:00, on every 2nd day of the month."],
  ["0 0 2-31/2 * *", "unix", "At 00:00, on every 2nd day of the month from day 2."],
  ["0 0 5-25/5 * *", "unix", "At 00:00, on every 5th day of the month from day 5 through 25."],
  ["10-40/10 * * * *", "unix", "Every 10 minutes from minute 10 through 40."],
  ["5/20 * * * *", "kubernetes", "At minutes 5, 25 and 45 of every hour."],
  ["0 0 0 13 * MON-FRI", "spring", "At 00:00, on day 13 of the month if it falls on Monday through Friday."],
  ["0 12 * 1 ? 2026", "aws", "At 12:00, in January 2026."],
  ["0 12 * 1,6 ? 2026-2028", "aws", "At 12:00, in January and June of 2026 through 2028."],
  ["0 0 0 1 1 ? 2030/2", "quartz", "At 00:00, on day 1 of the month, in January of every 2nd year from 2030."],
  ["0 0 0 1 * ? 2030/2", "quartz", "At 00:00, on day 1 of the month, in every 2nd year from 2030."],
  // Weekdays are listed Monday first, so Sunday comes last.
  ["0 0 * * 6,0", "unix", "At 00:00, on Saturday and Sunday."],
  ["0 0 * * 0,1,3", "unix", "At 00:00, on Monday, Wednesday and Sunday."],
  ["0 0 * * 5-7", "unix", "At 00:00, Friday through Sunday."],
  ["0 0 0 * * */2", "spring", "At 00:00, on Monday, Wednesday, Friday and Sunday."],
  ["0 0 12 ? * 1,7", "quartz", "At 12:00, on Saturday and Sunday."],
  ["@daily", "unix", "At 00:00."],
  ["@weekly", "unix", "At 00:00, on Sunday."],
];

for (const [expr, flavour, expected] of EXTRA) {
  test(`extra ${flavour}: ${expr}`, () => assert.equal(say(expr, flavour), expected));
}

test("star step on one day field combined with the other is AND", () => {
  assert.ok(say("0 0 */2 * 1", "unix").endsWith("if it falls on a Monday."));
});

test("sentences are well formed for varied expressions in every flavour", () => {
  const cases = {
    unix: ["* * * * *", "1,2,3,4,5 * * * *", "0 0 29 2 *", "0-30/10 1-3 1,15 JAN-MAR 1-5", "@monthly", "@reboot", "59 23 31 12 6"],
    kubernetes: ["* * * * *", "*/7 */5 ? * *", "0 0 1 1 ?", "@hourly", "0,30 8-18 * * mon-fri"],
    github: ["*/5 * * * *", "0 0 * * 0", "15 3 1 */2 *", "0,30 6,18 * * 1"],
    quartz: ["0 0 12 * * ?", "* * * * * ?", "0 0/5 14,18 * * ?", "0 15 10 ? * MON-FRI 2026-2030", "0 0 0 L-1 * ?", "0 0 8 ? * 2#1", "0 0 8 ? * 7L", "0 0 8 1W * ?", "0 0 8 LW 6 ? */2", "5,10,15 */2 * * * ?"],
    aws: ["0 12 * * ? *", "*/15 8-17 ? * MON-FRI *", "0 0 1 * ? 2027,2029", "0 18 ? * 6L *", "0 10 ? * 2#3 2030-2150"],
    spring: ["0 * * * * *", "*/5 */5 */5 * * *", "0 0 9-17 * * MON-FRI", "0 0 0 1 1 ?", "0 30 4 1,15 * 5", "@yearly"],
  };
  let count = 0;
  for (const [flavour, exprs] of Object.entries(cases)) {
    for (const expr of exprs) {
      const r = parse(expr, flavour);
      assert.ok(r.ok, `${flavour} ${expr}: ${r.error}`);
      const s = explain(r.cron);
      assert.ok(s.length > 1, `${flavour} ${expr}: empty`);
      assert.ok(s.endsWith("."), `${flavour} ${expr}: ${s}`);
      assert.ok(!/undefined|NaN|\[object/.test(s), `${flavour} ${expr}: ${s}`);
      count++;
    }
  }
  assert.ok(count >= 30);
});
