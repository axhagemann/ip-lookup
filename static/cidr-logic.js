/* CIDR parsing/formatting/range math. Loaded as a plain <script> in the
 * browser (attaches `window.CidrCalc`) and required as a CommonJS module
 * from the Node test runner — no build step either way. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.CidrCalc = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  function parseIPv4(ip) {
    const parts = ip.split(".");
    if (parts.length !== 4) return null;
    let result = 0n;
    for (const p of parts) {
      if (!/^\d{1,3}$/.test(p)) return null;
      const n = parseInt(p, 10);
      if (n > 255) return null;
      result = (result << 8n) | BigInt(n);
    }
    return result;
  }

  function formatIPv4(n) {
    const parts = [];
    for (let i = 3; i >= 0; i--) {
      parts.push(Number((n >> BigInt(i * 8)) & 0xffn));
    }
    return parts.join(".");
  }

  function parseIPv6(ip) {
    if (ip.indexOf(":") === -1) return null;

    let address = ip;
    const lastColon = address.lastIndexOf(":");
    const tailToken = address.slice(lastColon + 1);
    if (tailToken.indexOf(".") !== -1) {
      const v4 = parseIPv4(tailToken);
      if (v4 === null) return null;
      const hi = ((v4 >> 16n) & 0xffffn).toString(16);
      const lo = (v4 & 0xffffn).toString(16);
      address = address.slice(0, lastColon + 1) + hi + ":" + lo;
    }

    const doubleColonParts = address.split("::");
    if (doubleColonParts.length > 2) return null;

    let head = doubleColonParts[0] ? doubleColonParts[0].split(":") : [];
    let tail = [];
    let groups;

    if (doubleColonParts.length === 1) {
      groups = head;
      if (groups.length !== 8) return null;
    } else {
      tail = doubleColonParts[1] ? doubleColonParts[1].split(":") : [];
      const missing = 8 - head.length - tail.length;
      if (missing < 1) return null;
      groups = head.concat(new Array(missing).fill("0")).concat(tail);
    }

    if (groups.length !== 8) return null;

    let result = 0n;
    for (const g of groups) {
      if (!/^[0-9a-fA-F]{1,4}$/.test(g)) return null;
      result = (result << 16n) | BigInt(parseInt(g, 16));
    }
    return result;
  }

  function formatIPv6(n) {
    const groups = [];
    for (let i = 7; i >= 0; i--) {
      groups.push(((n >> BigInt(i * 16)) & 0xffffn).toString(16));
    }

    let bestStart = -1, bestLen = 0, curStart = -1, curLen = 0;
    for (let i = 0; i < 8; i++) {
      if (groups[i] === "0") {
        if (curStart === -1) curStart = i;
        curLen++;
        if (curLen > bestLen) { bestLen = curLen; bestStart = curStart; }
      } else {
        curStart = -1;
        curLen = 0;
      }
    }

    if (bestLen > 1) {
      const before = groups.slice(0, bestStart);
      const after = groups.slice(bestStart + bestLen);
      return before.join(":") + "::" + after.join(":");
    }
    return groups.join(":");
  }

  function computeRange(ipStr, prefix) {
    const isV6 = ipStr.indexOf(":") !== -1;
    const bits = isV6 ? 128 : 32;

    if (!Number.isInteger(prefix) || prefix < 0 || prefix > bits) {
      return { error: `Prefix must be between 0 and ${bits} for ${isV6 ? "IPv6" : "IPv4"}.` };
    }

    const ipInt = isV6 ? parseIPv6(ipStr) : parseIPv4(ipStr);
    if (ipInt === null) {
      return { error: `"${ipStr}" is not a valid ${isV6 ? "IPv6" : "IPv4"} address.` };
    }

    const full = (1n << BigInt(bits)) - 1n;
    const hostBits = BigInt(bits - prefix);
    const mask = hostBits === 0n ? full : (full << hostBits) & full;
    const network = ipInt & mask;
    const last = network | (~mask & full);

    return {
      start: isV6 ? formatIPv6(network) : formatIPv4(network),
      end: isV6 ? formatIPv6(last) : formatIPv4(last),
    };
  }

  return { parseIPv4, formatIPv4, parseIPv6, formatIPv6, computeRange };
});
