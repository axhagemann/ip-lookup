const test = require("node:test");
const assert = require("node:assert/strict");
const { computeRange } = require("../static/cidr-logic.js");

test("IPv4 /24", () => {
  assert.deepEqual(computeRange("192.168.1.130", 24), {
    start: "192.168.1.0",
    end: "192.168.1.255",
  });
});

test("IPv4 /8", () => {
  assert.deepEqual(computeRange("10.0.0.5", 8), {
    start: "10.0.0.0",
    end: "10.255.255.255",
  });
});

test("IPv4 /32 is a single address", () => {
  assert.deepEqual(computeRange("192.168.1.1", 32), {
    start: "192.168.1.1",
    end: "192.168.1.1",
  });
});

test("IPv4 /0 spans the whole address space", () => {
  assert.deepEqual(computeRange("0.0.0.0", 0), {
    start: "0.0.0.0",
    end: "255.255.255.255",
  });
});

test("rejects an invalid IPv4 octet", () => {
  const result = computeRange("999.1.1.1", 24);
  assert.ok(result.error);
});

test("rejects an out-of-range IPv4 prefix", () => {
  const result = computeRange("192.168.1.1", 33);
  assert.ok(result.error);
});

test("IPv6 /32", () => {
  assert.deepEqual(computeRange("2001:db8::1", 32), {
    start: "2001:db8::",
    end: "2001:db8:ffff:ffff:ffff:ffff:ffff:ffff",
  });
});

test("IPv6 /64 compresses the trailing zero run", () => {
  assert.deepEqual(computeRange("2001:db8:85a3::8a2e:370:7334", 64), {
    start: "2001:db8:85a3::",
    end: "2001:db8:85a3:0:ffff:ffff:ffff:ffff",
  });
});

test("IPv6 embedded IPv4-mapped address", () => {
  assert.deepEqual(computeRange("::ffff:192.168.1.1", 96), {
    start: "::ffff:0:0",
    end: "::ffff:ffff:ffff",
  });
});

test("rejects an out-of-range IPv6 prefix", () => {
  const result = computeRange("2001:db8::1", 200);
  assert.ok(result.error);
});
