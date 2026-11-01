/* Cron parsing, explaining, scheduling and conversion. Loaded as a plain
 * <script> in the browser (attaches `window.CronCalc`) and required as a
 * CommonJS module from the Node test runner — no build step either way. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.CronCalc = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  const MAX_LENGTH = 512;
  const MAX_ITEMS = 64;
  const MAX_DIGITS = 4;
  const MAX_ECHO = 20;

  const MACROS_ALL = ["@yearly", "@annually", "@monthly", "@weekly", "@daily", "@midnight", "@hourly"];
  // Expansions in 5-field (minute-based) form; seconds-based flavours get "0 " prepended.
  const MACRO_EXPANSIONS = {
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
    "@monthly": "0 0 1 * *",
    "@weekly": "0 0 * * 0",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@hourly": "0 * * * *",
  };

  const FIELD_LABELS = {
    second: "second",
    minute: "minute",
    hour: "hour",
    dom: "day of month",
    month: "month",
    dow: "day of week",
    year: "year",
  };
  const FIELD_HYPHENATED = { dom: "day-of-month", dow: "day-of-week" };

  const FIVE = ["minute", "hour", "dom", "month", "dow"];
  const SIX = ["second", ...FIVE];
  const SEVEN = [...SIX, "year"];

  const FLAVOURS = [
    {
      id: "unix",
      label: "Unix cron",
      fields: FIVE,
      optionalYear: false,
      dowBase: 0,
      dowAllowsSeven: true,
      question: "none",
      specials: false,
      macros: [...MACROS_ALL, "@reboot"],
      dayMatch: "or",
      starRule: "vixie",
      yearRange: null,
      utcOnly: false,
      minIntervalMinutes: null,
    },
    {
      id: "kubernetes",
      label: "Kubernetes CronJob",
      fields: FIVE,
      optionalYear: false,
      dowBase: 0,
      dowAllowsSeven: false,
      question: "alias",
      specials: false,
      macros: MACROS_ALL,
      dayMatch: "or",
      starRule: "robfig",
      yearRange: null,
      utcOnly: false,
      minIntervalMinutes: null,
    },
    {
      id: "github",
      label: "GitHub Actions",
      fields: FIVE,
      optionalYear: false,
      dowBase: 0,
      dowAllowsSeven: false,
      question: "none",
      specials: false,
      macros: [],
      dayMatch: "or",
      starRule: "vixie",
      yearRange: null,
      utcOnly: true,
      minIntervalMinutes: 5,
    },
    {
      id: "quartz",
      label: "Quartz",
      fields: SEVEN,
      optionalYear: true,
      dowBase: 1,
      dowAllowsSeven: false,
      question: "required",
      specials: true,
      macros: [],
      dayMatch: "single",
      starRule: "none",
      yearRange: [1970, 2099],
      utcOnly: false,
      minIntervalMinutes: null,
    },
    {
      id: "aws",
      label: "AWS EventBridge",
      fields: ["minute", "hour", "dom", "month", "dow", "year"],
      optionalYear: false,
      dowBase: 1,
      dowAllowsSeven: false,
      question: "required",
      specials: true,
      macros: [],
      dayMatch: "single",
      starRule: "none",
      yearRange: [1970, 2199],
      utcOnly: true,
      minIntervalMinutes: null,
    },
    {
      id: "spring",
      label: "Spring",
      fields: SIX,
      optionalYear: false,
      dowBase: 0,
      dowAllowsSeven: true,
      question: "alias",
      specials: true,
      macros: MACROS_ALL,
      dayMatch: "and",
      starRule: "none",
      monBasedDowSteps: true, // Spring counts day-of-week 1-7 (Mon=1, Sun=7), so "*" and "a/n" step from Monday
      yearRange: null,
      utcOnly: false,
      minIntervalMinutes: null,
    },
  ];

  function getFlavour(id) {
    const f = FLAVOURS.find((x) => x.id === id);
    if (!f) throw new Error("Unknown flavour: " + id);
    return f;
  }

  const MONTH_NAMES = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];
  const DOW_NAMES = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];

  // Thrown internally to abort parsing with a user-facing message.
  class CronError extends Error {
    constructor(message, field) {
      super(message);
      this.field = field === undefined ? null : field;
    }
  }

  function echo(token) {
    return token.length > MAX_ECHO ? token.slice(0, MAX_ECHO) + "…" : token;
  }

  function isAsciiSpace(ch) {
    return ch === " " || ch === "\t" || ch === "\r" || ch === "\n";
  }

  // ASCII-only trim: String.trim() would also swallow NBSP, which must be rejected.
  function trimAscii(s) {
    let start = 0;
    let end = s.length;
    while (start < end && isAsciiSpace(s[start])) start++;
    while (end > start && isAsciiSpace(s[end - 1])) end--;
    return s.slice(start, end);
  }

  const ALLOWED = /^[A-Za-z0-9 \t*?,\-/#@()_=]*$/;

  function describeChar(ch) {
    const code = ch.codePointAt(0);
    const printable = code >= 0x21 && code <= 0x7e;
    // Invisible, whitespace or control characters are shown as a code point.
    if (printable || !/[\p{C}\p{Z}\p{M}]/u.test(ch)) return '"' + ch + '"';
    return "U+" + code.toString(16).toUpperCase().padStart(4, "0");
  }

  function checkCharacters(s) {
    if (ALLOWED.test(s)) return;
    let pos = 0;
    for (const ch of s) {
      pos++;
      if (!ALLOWED.test(ch)) {
        throw new CronError("Unsupported character " + describeChar(ch) + " at position " + pos + ".");
      }
    }
  }

  function fieldOrderHint(flavour) {
    const names = flavour.fields.map((n) => FIELD_HYPHENATED[n] || n);
    if (flavour.optionalYear) names[names.length - 1] = "[" + names[names.length - 1] + "]";
    return names.join(" ");
  }

  // Native (as typed) numeric bounds for a field in this flavour.
  function bounds(name, flavour) {
    switch (name) {
      case "second":
      case "minute":
        return [0, 59];
      case "hour":
        return [0, 23];
      case "dom":
        return [1, 31];
      case "month":
        return [1, 12];
      case "dow":
        return [flavour.dowBase, flavour.dowAllowsSeven ? 7 : flavour.dowBase + 6];
      default:
        return flavour.yearRange;
    }
  }

  // Upper bound used for "*" and "a/n" (7 is only an alias for Sunday there).
  function naturalMax(name, flavour, b) {
    return name === "dow" ? flavour.dowBase + 6 : b[1];
  }

  function names(name, flavour) {
    if (name === "month") return { list: MONTH_NAMES, offset: 1 };
    if (name === "dow") return { list: DOW_NAMES, offset: flavour.dowBase };
    return null;
  }

  function toCanonicalDow(v, flavour) {
    if (flavour.dowBase === 1) return v - 1;
    return v === 7 ? 0 : v;
  }

  function range(lo, hi, step) {
    const out = [];
    for (let v = lo; v <= hi; v += step) out.push(v);
    return out;
  }

  // Parses one field. Returns a FieldSpec.
  function parseField(raw, name, index, flavour) {
    const where = "Field " + index + " (" + FIELD_LABELS[name] + "): ";
    const fail = (msg) => new CronError(where + msg, name);
    const b = bounds(name, flavour);
    const max = naturalMax(name, flavour, b);
    const rangeText = b[0] + "–" + b[1];
    const nameInfo = names(name, flavour);
    const isDay = name === "dom" || name === "dow";

    const number = (txt) => {
      if (/^[0-9]+$/.test(txt)) {
        if (txt.length > MAX_DIGITS) throw fail("number " + echo(txt) + " is too long.");
        return Number(txt);
      }
      const i = nameInfo ? nameInfo.list.indexOf(txt.toUpperCase()) : -1;
      if (i >= 0) return i + nameInfo.offset;
      throw fail('invalid value "' + echo(txt) + '".');
    };
    const inRange = (v, txt, lo = b[0], hi = b[1], text = rangeText) => {
      if (v < lo || v > hi) throw fail(echo(txt) + " is out of range " + text + ".");
      return v;
    };
    const dowNative = (txt) => inRange(number(txt), txt);

    const finish = (values, special) => {
      let vals = values;
      if (name === "dow") vals = vals.map((v) => toCanonicalDow(v, flavour));
      vals = [...new Set(vals)].sort((x, y) => x - y);
      return {
        raw,
        star: raw.startsWith("*"),
        question: raw === "?",
        values: vals,
        special: special || null,
      };
    };
    const full = () => range(b[0], max, 1);
    // Spring day-of-week steps run through 1..7 (Mon..Sun), with 0 folded into 7.
    const monSteps = name === "dow" && flavour.monBasedDowSteps === true;
    const stepLo = monSteps ? 1 : b[0];
    const stepHi = monSteps ? 7 : max;

    if (raw === "?") {
      if (!isDay) throw fail("? is only allowed in day of month and day of week.");
      if (flavour.question === "none") throw fail("? is not supported by " + flavour.label + ".");
      return finish(full());
    }

    const items = raw.split(",");
    if (items.length > MAX_ITEMS) throw fail("too many values (max " + MAX_ITEMS + ").");

    const upper = raw.toUpperCase();
    const looksSpecial =
      (name === "dom" && !raw.includes("/") && /[LW]/.test(upper)) ||
      (name === "dow" && (raw.includes("#") || (upper.endsWith("L") && !raw.includes("/"))));
    if (looksSpecial) {
      if (!flavour.specials) throw fail(echo(raw) + " is not supported by " + flavour.label + ".");
      if (items.length > 1) throw fail(echo(raw) + " can't be combined with other values.");
      return finish([], parseSpecial(raw, upper));
    }

    function parseSpecial(text, up) {
      if (name === "dom") {
        if (up === "L") return { type: "last", offset: 0 };
        if (up === "LW") return { type: "lastWeekday" };
        let m = /^L-([0-9]+)$/.exec(up);
        if (m) {
          const offset = inRange(number(m[1]), m[1], 1, 30, "1–30");
          return { type: "last", offset };
        }
        m = /^([0-9]+)W$/.exec(up);
        if (m) return { type: "nearestWeekday", day: inRange(number(m[1]), m[1], 1, 31, "1–31") };
        throw fail('invalid value "' + echo(text) + '".');
      }
      const hash = text.indexOf("#");
      if (hash >= 0) {
        const nthTxt = text.slice(hash + 1);
        const dow = dowNative(text.slice(0, hash));
        const nth = inRange(number(nthTxt), nthTxt, 1, 5, "1–5");
        return { type: "nthDow", dow: toCanonicalDow(dow, flavour), nth };
      }
      const head = text.slice(0, -1);
      if (head === "") throw fail('invalid value "' + echo(text) + '".');
      return { type: "lastDow", dow: toCanonicalDow(dowNative(head), flavour) };
    }

    const values = [];
    for (const item of items) {
      if (item === "") throw fail("empty value in list.");
      const slash = item.indexOf("/");
      let step = 1;
      let stepGiven = false;
      let base = item;
      if (slash >= 0) {
        base = item.slice(0, slash);
        const stepTxt = item.slice(slash + 1);
        if (!/^[0-9]+$/.test(stepTxt)) throw fail('invalid step "' + echo(stepTxt) + '".');
        step = number(stepTxt);
        if (step < 1) throw fail("step must be at least 1.");
        stepGiven = true;
      }

      if (base === "*" || base === "?") {
        if (base === "?") throw fail('invalid value "' + echo(item) + '".');
        values.push(...range(stepLo, stepHi, step));
        continue;
      }

      const parts = base.split("-");
      if (parts.length > 2) throw fail('invalid value "' + echo(item) + '".');
      if (parts.length === 2) {
        const lo = inRange(number(parts[0]), parts[0]);
        const hi = inRange(number(parts[1]), parts[1]);
        if (lo > hi) throw fail("range " + echo(base) + " starts after it ends.");
        values.push(...range(lo, hi, step));
        continue;
      }

      const v = inRange(number(base), base);
      if (!stepGiven) {
        values.push(v);
        continue;
      }
      if (flavour.question === "none") {
        throw fail(
          echo(item) + " isn't supported by " + flavour.label + "; use " + echo(base) + "-" + max + "/" + step + ".",
        );
      }
      values.push(...range(v, stepHi, step));
    }
    return finish(values);
  }

  function splitFields(text) {
    return text.split(/[ \t]+/);
  }

  function expectedCount(flavour) {
    const n = flavour.fields.length;
    const noun = flavour.optionalYear ? n - 1 + " or " + n : String(n);
    return noun + " fields (" + fieldOrderHint(flavour) + ")";
  }

  function parseMacro(text, flavour) {
    const tokens = splitFields(text);
    if (tokens.length > 1) throw new CronError("A macro can't be combined with other fields.");
    const macro = text.toLowerCase();
    if (!MACROS_ALL.includes(macro) && macro !== "@reboot") {
      throw new CronError('Unknown macro "' + echo(text) + '".');
    }
    if (!flavour.macros.includes(macro)) {
      throw new CronError(macro + " is not supported by " + flavour.label + ".");
    }
    const fields = {};
    for (const n of Object.keys(FIELD_LABELS)) fields[n] = null;
    if (macro === "@reboot") return { flavour: flavour.id, macro, reboot: true, fields };
    const expanded = (flavour.fields.includes("second") ? "0 " : "") + MACRO_EXPANSIONS[macro];
    const cron = parseFieldList(splitFields(expanded), flavour);
    cron.macro = macro;
    return cron;
  }

  function parseFieldList(tokens, flavour) {
    const fieldNames = flavour.fields.slice(0, tokens.length);
    const fields = {};
    for (const n of Object.keys(FIELD_LABELS)) fields[n] = null;
    fieldNames.forEach((n, i) => {
      fields[n] = parseField(tokens[i], n, i + 1, flavour);
    });
    if (flavour.optionalYear && !fields.year) {
      const [lo, hi] = flavour.yearRange;
      fields.year = { raw: "*", star: true, question: false, values: range(lo, hi, 1), special: null };
    }
    if (flavour.question === "required" && fields.dom.question === fields.dow.question) {
      throw new CronError(flavour.label + " requires ? in exactly one of day of month and day of week.");
    }
    return { flavour: flavour.id, macro: null, reboot: false, fields };
  }

  function parseOrThrow(expr, flavourId) {
    const flavour = getFlavour(flavourId);
    let text = trimAscii(String(expr));
    if (text === "") throw new CronError("Enter a cron expression.");
    if (text.length > MAX_LENGTH) throw new CronError("Expression is too long (max " + MAX_LENGTH + " characters).");
    checkCharacters(text);

    if (flavour.id === "aws" && text.slice(0, 5).toLowerCase() === "cron(" && text.endsWith(")")) {
      text = trimAscii(text.slice(5, -1));
    }

    const lower = text.toLowerCase();
    if (lower.startsWith("cron_tz=") || lower.startsWith("tz=")) {
      throw new CronError(
        flavour.id === "kubernetes"
          ? "Time zone prefixes aren't supported in the schedule; set spec.timeZone on the CronJob instead."
          : "Time zone prefixes aren't supported.",
      );
    }

    if (text.startsWith("@")) return parseMacro(text, flavour);

    const tokens = splitFields(text);
    const n = flavour.fields.length;
    const min = flavour.optionalYear ? n - 1 : n;
    if (tokens.length < min || tokens.length > n) {
      throw new CronError("Expected " + expectedCount(flavour) + ", got " + tokens.length + ".");
    }
    return parseFieldList(tokens, flavour);
  }

  function parse(expr, flavourId) {
    try {
      return { ok: true, cron: parseOrThrow(expr, flavourId) };
    } catch (e) {
      if (e instanceof CronError) return { ok: false, error: e.message, field: e.field };
      throw e;
    }
  }

  // Whether a day field counts as "open" (a star) when dom and dow are combined.
  // vixie (Unix, GitHub): the raw text starts with "*"; "?" is an alias for "*".
  // robfig (Kubernetes): robfig/cron clears its star bit for "*/n" with n > 1, so only
  //   "*", "?" or "*/1" as a comma item is open.
  // none (Quartz, AWS, Spring): never ORs; "*"-prefixed or "?" counts as open for conversion.
  function isOpenRaw(raw, flavour) {
    if (flavour.starRule === "robfig") {
      return raw.split(",").some((it) => it === "*" || it === "?" || it === "*/1");
    }
    return raw.startsWith("*") || raw === "?";
  }
  const isOpenDayField = (spec, flavour) => isOpenRaw(spec.raw, flavour);

  // ---- Next runs (UTC) ----------------------------------------------------
  const SEARCH_DAYS = 5 * 366;
  const DAY_MS = 86400000;

  function daysInMonth(year, month) {
    return new Date(Date.UTC(year, month, 0)).getUTCDate();
  }

  function weekdayOf(year, month, day) {
    return new Date(Date.UTC(year, month - 1, day)).getUTCDay();
  }

  // Day of month a "nW" lands on: the nearest weekday without leaving the month.
  function nearestWeekdayDay(year, month, day, dim) {
    if (day > dim) return -1;
    const wd = weekdayOf(year, month, day);
    if (wd === 6) return day === 1 ? 3 : day - 1;
    if (wd === 0) return day === dim ? day - 2 : day + 1;
    return day;
  }

  function domMatches(spec, year, month, day) {
    if (!spec.special) return spec.values.includes(day);
    const dim = daysInMonth(year, month);
    const sp = spec.special;
    if (sp.type === "last") return day === dim - sp.offset;
    if (sp.type === "lastWeekday") {
      const wd = weekdayOf(year, month, dim);
      return day === (wd === 6 ? dim - 1 : wd === 0 ? dim - 2 : dim);
    }
    return day === nearestWeekdayDay(year, month, sp.day, dim);
  }

  function dowMatches(spec, year, month, day) {
    const wd = weekdayOf(year, month, day);
    if (!spec.special) return spec.values.includes(wd);
    const sp = spec.special;
    if (wd !== sp.dow) return false;
    if (sp.type === "nthDow") return Math.ceil(day / 7) === sp.nth;
    return day + 7 > daysInMonth(year, month);
  }

  function dayMatches(flavour, fields, year, month, day) {
    const { dom, dow } = fields;
    if (flavour.dayMatch === "single") {
      return dom.question ? dowMatches(dow, year, month, day) : domMatches(dom, year, month, day);
    }
    const domOk = domMatches(dom, year, month, day);
    const dowOk = dowMatches(dow, year, month, day);
    if (flavour.dayMatch === "and") return domOk && dowOk;
    // Vixie "or": a star side (and "?" where it is an alias for "*") matches everything.
    const domOpen = isOpenDayField(dom, flavour);
    const dowOpen = isOpenDayField(dow, flavour);
    return domOpen || dowOpen ? domOk && dowOk : domOk || dowOk;
  }

  // The next `n` run times strictly after `from`, in UTC. Searches day by day
  // (never minute by minute) for at most five years.
  function nextRuns(cron, from, n = 5) {
    if (cron.reboot) return [];
    const flavour = getFlavour(cron.flavour);
    const f = cron.fields;
    const seconds = f.second ? f.second.values : [0];
    const fromMs = from.getTime();
    const start = new Date(fromMs);
    const startDay = Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), start.getUTCDate());
    const out = [];
    for (let i = 0; i < SEARCH_DAYS; i++) {
      const date = new Date(startDay + i * DAY_MS);
      const y = date.getUTCFullYear();
      const mo = date.getUTCMonth() + 1;
      const d = date.getUTCDate();
      if (f.year && !f.year.values.includes(y)) continue;
      if (!f.month.values.includes(mo)) continue;
      if (!dayMatches(flavour, f, y, mo, d)) continue;
      for (const h of f.hour.values) {
        for (const m of f.minute.values) {
          for (const s of seconds) {
            const t = Date.UTC(y, mo - 1, d, h, m, s);
            if (t > fromMs) {
              out.push(new Date(t));
              if (out.length >= n) return out;
            }
          }
        }
      }
    }
    return out;
  }

  // ---- Explain ------------------------------------------------------------
  const MONTH_LABELS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  const DOW_LABELS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  const NTH_WORDS = ["", "first", "second", "third", "fourth", "fifth"];

  // min/size describe the full range; `noun` is used in phrases, `label` names values.
  const SETS = {
    second: { min: 0, size: 60, noun: "second" },
    minute: { min: 0, size: 60, noun: "minute" },
    hour: { min: 0, size: 24, noun: "hour" },
    dom: { min: 1, size: 31, noun: "day" },
    month: { min: 1, size: 12, noun: "month", label: (v) => MONTH_LABELS[v - 1] },
    dow: { min: 0, size: 7, noun: "day", label: (v) => DOW_LABELS[v], noStep: true },
  };

  // Weekday numbers 1-7 with Sunday as 7, used to order weekday lists Monday first.
  const DOW_MONDAY_FIRST = { label: (v) => DOW_LABELS[v % 7] };

  function ordinal(n) {
    const t = n % 100;
    const suffix = t >= 11 && t <= 13 ? "th" : { 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th";
    return n + suffix;
  }

  function joinList(items, conj = "and") {
    if (items.length < 3) return items.join(" " + conj + " ");
    return items.slice(0, -1).join(", ") + " " + conj + " " + items[items.length - 1];
  }

  const isAll = (spec, set) => !spec.special && spec.values.length === set.size;
  const labelOf = (set, v) => (set.label ? set.label(v) : String(v));

  // Classifies a field's values as all of them, an even step, or a plain list.
  // A step's `from`/`to` are null when it starts at the range's first value or
  // runs on to its end; `cycle` means it also divides the range evenly.
  function describeSet(spec, set) {
    const v = spec.values;
    const n = v.length;
    if (!spec.special && n === set.size) return { kind: "all" };
    if (n >= 2 && !set.noStep) {
      const step = v[1] - v[0];
      const even = step > 1 && v.every((x, i) => i === 0 || x - v[i - 1] === step);
      if (even) {
        const from = v[0] === set.min ? null : v[0];
        const to = v[n - 1] + step > set.min + set.size - 1 ? null : v[n - 1];
        const cycle = from === null && to === null && set.size % step === 0;
        if (from === null && to === null && (n >= 3 || spec.raw.startsWith("*/"))) return { kind: "step", step, cycle, from, to };
        if (n >= 4) return { kind: "step", step, cycle, from, to };
      }
    }
    return { kind: "list" };
  }

  // "1, 3 and 5-8" style text; runs of three or more become "X through Y".
  function listText(values, set, conj = "and") {
    const items = [];
    for (let i = 0; i < values.length; ) {
      let j = i;
      while (j + 1 < values.length && values[j + 1] === values[j] + 1) j++;
      if (j - i >= 2) items.push(labelOf(set, values[i]) + " through " + labelOf(set, values[j]));
      else for (let k = i; k <= j; k++) items.push(labelOf(set, values[k]));
      i = j + 1;
    }
    return { text: joinList(items, conj), through: items.length === 1 && values.length > 2 };
  }

  // " from hour 8 through 18" / " from day 2" / "" for a step's bounds.
  function rangeText(d, set) {
    const pre = set.label || set.bare ? "" : set.noun + " ";
    if (d.from === null && d.to === null) return "";
    const from = labelOf(set, d.from === null ? set.min : d.from);
    return " from " + pre + from + (d.to === null ? "" : " through " + labelOf(set, d.to));
  }

  // "every 2nd hour" / "every 5th hour from hour 8 through 18"
  function stepText(d, set) {
    return "every " + ordinal(d.step) + " " + set.noun + rangeText(d, set);
  }

  // One time unit. As the head it opens the sentence; as a tail it follows with `word`.
  function unitPhrase(spec, set, head, word) {
    const d = describeSet(spec, set);
    const noun = set.noun;
    if (head) {
      if (d.kind === "all") return "Every " + noun;
      if (d.kind === "step") {
        // A step that runs to the end of the range without dividing it restarts
        // early (*/7 minutes: ...:49, :56, then :00), so "every 7 minutes" would mislead.
        if (d.to === null && !d.cycle) return "At every " + ordinal(d.step) + " " + noun + rangeText(d, set);
        return "Every " + d.step + " " + noun + "s" + rangeText(d, set);
      }
      return "At " + noun + (spec.values.length > 1 ? "s " : " ") + listText(spec.values, set).text;
    }
    if (d.kind === "all") return "";
    if (d.kind === "step") return word + " " + stepText(d, set);
    return word + " " + noun + (spec.values.length > 1 ? "s " : " ") + listText(spec.values, set).text;
  }

  const pad2 = (n) => String(n).padStart(2, "0");

  function timePart(f) {
    const secs = f.second ? f.second.values : [0];
    const withSeconds = secs.some((s) => s !== 0);
    const hours = f.hour.values;
    const minutes = f.minute.values;
    if (hours.length * minutes.length * secs.length <= 4) {
      const times = [];
      for (const h of hours) {
        for (const m of minutes) {
          for (const s of secs) times.push(pad2(h) + ":" + pad2(m) + (withSeconds ? ":" + pad2(s) : ""));
        }
      }
      return "At " + joinList(times);
    }
    const chain = (withSeconds ? ["second", "minute", "hour"] : ["minute", "hour"]).map((n) => [n, f[n], SETS[n]]);
    const [, headSpec, headSet] = chain[0];
    const head = unitPhrase(headSpec, headSet, true);
    const every = head.startsWith("Every") || head.startsWith("At every");
    let out = head;
    chain.slice(1).forEach(([name, spec, set], i) => {
      if (isAll(spec, set)) {
        if (i === 0 && !every) out += " of every " + set.noun;
        return;
      }
      out += " " + unitPhrase(spec, set, false, name === "hour" && every ? "during" : "past");
    });
    return out;
  }

  // Phrases are { text, on }: `on` says whether "on " may precede the text.
  const withOn = (p) => (p.on ? "on " : "") + p.text;

  function domPhrase(spec) {
    const sp = spec.special;
    if (!sp && spec.values.length === 0) return { text: "no day of the month", on: false };
    if (sp) {
      if (sp.type === "lastWeekday") return { text: "the last weekday of the month", on: true };
      if (sp.type === "nearestWeekday") return { text: "the weekday nearest day " + sp.day + " of the month", on: true };
      if (sp.offset === 0) return { text: "the last day of the month", on: true };
      return { text: sp.offset + " day" + (sp.offset > 1 ? "s" : "") + " before the last day of the month", on: false };
    }
    const d = describeSet(spec, SETS.dom);
    if (d.kind === "step") return { text: "every " + ordinal(d.step) + " day of the month" + rangeText(d, SETS.dom), on: true };
    return { text: "day" + (spec.values.length > 1 ? "s " : " ") + listText(spec.values, SETS.dom).text + " of the month", on: true };
  }

  function dowPhrase(spec, conj) {
    const sp = spec.special;
    if (!sp && spec.values.length === 0) return { text: "no day of the week", on: false };
    if (sp) {
      const nth = sp.type === "nthDow" ? NTH_WORDS[sp.nth] : "last";
      return { text: "the " + nth + " " + DOW_LABELS[sp.dow] + " of the month", on: true };
    }
    // List weekdays Monday first (Sunday last), so 0 is placed after 6.
    const mondayFirst = spec.values.map((d) => (d === 0 ? 7 : d)).sort((x, y) => x - y);
    const l = listText(mondayFirst, DOW_MONDAY_FIRST, conj);
    return { text: l.text, on: !l.through };
  }

  function dayPart(flavour, f) {
    const { dom, dow } = f;
    const domAll = isAll(dom, SETS.dom);
    const dowAll = isAll(dow, SETS.dow);
    if (domAll && dowAll) return "";
    if (domAll) return withOn(dowPhrase(dow, "and"));
    if (dowAll) return withOn(domPhrase(dom));
    // Vixie cron ORs the two only when neither starts with "*"; Spring always ANDs.
    if (flavour.dayMatch === "or" && !isOpenDayField(dom, flavour) && !isOpenDayField(dow, flavour)) {
      return withOn(domPhrase(dom)) + " or " + withOn(dowPhrase(dow, "and"));
    }
    const p = dowPhrase(dow, "or");
    const single = !dow.special && dow.values.length === 1;
    return withOn(domPhrase(dom)) + " if it falls on " + (single ? "a " : "") + p.text;
  }

  // "January and June" / "every 3rd month" / "2027 through 2030" / "" for all.
  function periodText(spec, set) {
    const d = describeSet(spec, set);
    if (d.kind === "all") return "";
    if (d.kind === "step") return stepText(d, set);
    return listText(spec.values, set).text;
  }

  // "in January", "in 2027", "in January 2026", "in March of every 2nd year from 2030"
  function monthYearPart(f, yearSet) {
    const months = periodText(f.month, SETS.month);
    const years = f.year ? periodText(f.year, yearSet) : "";
    if (!months || !years) return months || years ? "in " + (months || years) : "";
    const singleYear = f.year.values.length === 1;
    const monthStep = describeSet(f.month, SETS.month).kind === "step";
    return "in " + months + (singleYear && !monthStep ? " " : " of ") + years;
  }

  // One English sentence describing when `cron` runs. Times are UTC.
  function explain(cron) {
    if (cron.reboot) return "At system startup.";
    const flavour = getFlavour(cron.flavour);
    const f = cron.fields;
    const yearSet = f.year && { min: flavour.yearRange[0], size: flavour.yearRange[1] - flavour.yearRange[0] + 1, noun: "year", bare: true };
    const parts = [timePart(f), dayPart(flavour, f), monthYearPart(f, yearSet)];
    return parts.filter(Boolean).join(", ") + ".";
  }

  // ---- Convert ------------------------------------------------------------
  // Policy: same run set => convert silently; time shifted, days unchanged =>
  // convert with a warning; different run set => refuse with the reason.
  const RANGE_REWRITE_TARGETS = ["unix", "kubernetes", "github"]; // no "a/n" start-step
  const FIELD_MAX = { minute: 59, hour: 23, dom: 31, month: 12 };
  const DOM_COUNT = 31;
  const DOW_COUNT = 7;

  class ConvertRefusal extends Error {}
  const refuse = (msg) => new ConvertRefusal(msg);

  // "a/n" -> "a-max/n" in each comma item whose base is a single value.
  function rewriteStartStep(raw, max) {
    return raw
      .split(",")
      .map((item) => {
        const m = /^([^-*/]+)\/(.+)$/.exec(item);
        return m ? m[1] + "-" + max + "/" + m[2] : item;
      })
      .join(",");
  }

  // Matches every day on its own: can be replaced by "?" without changing anything.
  const isFullyOpen = (spec, count, flavour) => isOpenDayField(spec, flavour) && !spec.special && spec.values.length === count;

  // How dom and dow combine, given each side's open-ness under `flavour`'s star rule.
  const modeOf = (domOpen, dowOpen, flavour) => (flavour.dayMatch === "or" && !domOpen && !dowOpen ? "or" : "and");
  function dayMode(src, f) {
    return modeOf(isOpenDayField(f.dom, src), isOpenDayField(f.dow, src), src);
  }

  // "*/n" items -> "lo-hi/n" so a Kubernetes OR stays an OR in a Vixie flavour.
  const closeStarSteps = (raw, lo, hi) =>
    raw
      .split(",")
      .map((it) => {
        const m = /^\*\/([0-9]+)$/.exec(it);
        return m ? lo + "-" + hi + "/" + m[1] : it;
      })
      .join(",");

  // Both sides are OR-capable: the day mode must survive the new star rule.
  function reconcileDayMode(src, tgt, f, out) {
    const before = dayMode(src, f);
    const after = () => modeOf(isOpenRaw(out.dom, tgt), isOpenRaw(out.dow, tgt), tgt);
    if (before === "or" && after() === "and") {
      out.dom = closeStarSteps(out.dom, 1, 31);
      out.dow = closeStarSteps(out.dow, tgt.dowBase, tgt.dowBase + 6);
    }
    if (after() !== before) {
      throw refuse(
        tgt.label + " reads the day fields differently (runs when either the day of month or the day of week matches), so this can't be converted without changing when it runs.",
      );
    }
  }

  function checkDayMode(src, tgt, f) {
    if (dayMode(src, f) === "or") {
      if (tgt.dayMatch !== "or") {
        throw refuse(
          tgt.label +
            ' can\'t express "day of month X or weekday Y" in one expression; split it into two schedules, one by day of month and one by weekday.',
        );
      }
    } else if (tgt.dayMatch === "or" && src.dayMatch !== "or" && !isOpenDayField(f.dom, src) && !isOpenDayField(f.dow, src)) {
      throw refuse(
        tgt.label + " runs when either the day of month or the day of week matches, so this can't be converted without changing when it runs.",
      );
    } else if (tgt.dayMatch === "single" && !isFullyOpen(f.dom, DOM_COUNT, src) && !isFullyOpen(f.dow, DOW_COUNT, src)) {
      throw refuse(
        tgt.label + " can't require both a day of month and a day of week to match, so this can't be converted without changing when it runs.",
      );
    }
  }

  const canonicalOfDowToken = (tok, src) =>
    /^[0-9]+$/.test(tok) ? toCanonicalDow(Number(tok), src) : DOW_NAMES.indexOf(tok.toUpperCase());

  // One numeric dow token in source numbering -> target numbering (names stay names).
  function dowToken(tok, src, tgt) {
    return /^[0-9]+$/.test(tok) ? String(canonicalOfDowToken(tok, src) + tgt.dowBase) : tok;
  }

  function explicitDowList(item, src, tgt) {
    const values = parseField(item, "dow", 1, src).values;
    return values.map((v) => v + tgt.dowBase).join(",");
  }

  function convertDowItem(item, src, tgt, renumber) {
    if (!renumber) return item;
    // Keep a leading "*" (with or without step): it is what makes Vixie flavours AND the day fields.
    if (item.startsWith("*") && src.dowBase === tgt.dowBase) return item;
    if (item === "*") return item;
    if (item.includes("/")) return explicitDowList(item, src, tgt);
    const parts = item.split("-");
    if (parts.length === 2) {
      // A range ending in 7 (Sunday) can't be a single range once Sunday is renumbered.
      const sevenEnd = src.dowAllowsSeven && !tgt.dowAllowsSeven && parts[1] === "7";
      return sevenEnd ? explicitDowList(item, src, tgt) : parts.map((p) => dowToken(p, src, tgt)).join("-");
    }
    return dowToken(item, src, tgt);
  }

  function convertDow(spec, src, tgt) {
    if (spec.question) return "*";
    const renumber = src.dowBase !== tgt.dowBase || (src.dowAllowsSeven && !tgt.dowAllowsSeven);
    // Spring steps from Monday and everyone else from Sunday: spell steps out as lists.
    const springEdge = (src.id === "spring") !== (tgt.id === "spring");
    if (spec.special) {
      const m = /^([^#]+?)(L|#.*)$/i.exec(spec.raw);
      return dowToken(m[1], src, tgt) + m[2];
    }
    let raw = spec.raw;
    if (!renumber && !springEdge && RANGE_REWRITE_TARGETS.includes(tgt.id)) raw = rewriteStartStep(raw, tgt.dowBase + 6);
    return raw
      .split(",")
      .map((item) => (springEdge && item.includes("/") ? explicitDowList(item, src, tgt) : convertDowItem(item, src, tgt, renumber)))
      .join(",");
  }

  function convertSecond(spec, src, tgt, warnings) {
    if (tgt.fields.includes("second")) return src.fields.includes("second") ? spec.raw : "0";
    if (!src.fields.includes("second")) return null;
    if (spec.values.length !== 1) {
      throw refuse(
        tgt.label + " has no seconds field and this schedule runs more than once a minute, so it can't be converted.",
      );
    }
    const s = spec.values[0];
    if (s !== 0) {
      warnings.push(tgt.label + " has no seconds field, so this will run at :00 instead of :" + pad2(s) + ".");
    }
    return null;
  }

  function convertYear(spec, src, tgt) {
    const star = !spec || spec.raw === "*";
    if (!tgt.yearRange) {
      if (!star) throw refuse(tgt.label + " has no year field, so a specific year can't be converted.");
      return null;
    }
    if (star) return tgt.optionalYear ? null : "*";
    const [lo, hi] = tgt.yearRange;
    if (spec.values.some((y) => y < lo || y > hi)) {
      throw refuse("The year is outside the " + lo + "–" + hi + " range that " + tgt.label + " supports.");
    }
    return spec.raw;
  }

  function checkSpecial(spec, name, tgt) {
    if (spec.special && !tgt.specials) {
      throw refuse(tgt.label + ' doesn\'t support "' + spec.raw + '" in the ' + FIELD_LABELS[name] + " field.");
    }
  }

  // GitHub-style minimum interval: warn when two runs can be closer than the minimum.
  function intervalWarning(f, tgt) {
    const min = tgt.minIntervalMinutes;
    if (!min) return null;
    const m = f.minute.values;
    let tight = m.some((v, i) => i > 0 && v - m[i - 1] < min);
    if (f.hour.values.length !== 1 && 60 - m[m.length - 1] + m[0] < min) tight = true;
    return tight ? tgt.label + " won't run schedules more often than every " + min + " minutes." : null;
  }

  function convertCron(cron, src, tgt) {
    if (cron.reboot) throw refuse("@reboot runs once at startup, which " + tgt.label + " has no equivalent for.");
    if (cron.macro && tgt.macros.includes(cron.macro)) return { expression: cron.macro, warnings: [] };

    const f = cron.fields;
    const warnings = [];
    checkSpecial(f.dom, "dom", tgt);
    checkSpecial(f.dow, "dow", tgt);
    checkDayMode(src, tgt, f);

    const out = {};
    out.second = convertSecond(f.second, src, tgt, warnings);
    const rewrite = RANGE_REWRITE_TARGETS.includes(tgt.id);
    for (const n of ["minute", "hour", "month"]) out[n] = rewrite ? rewriteStartStep(f[n].raw, FIELD_MAX[n]) : f[n].raw;
    out.dom = f.dom.question ? "*" : rewrite ? rewriteStartStep(f.dom.raw, FIELD_MAX.dom) : f.dom.raw;
    out.dow = convertDow(f.dow, src, tgt);
    if (tgt.dayMatch === "or") reconcileDayMode(src, tgt, f, out);
    if (tgt.question === "required") {
      if (isFullyOpen(f.dom, DOM_COUNT, src)) {
        if (isFullyOpen(f.dow, DOW_COUNT, src)) out.dow = "?";
        else out.dom = "?";
      } else {
        out.dow = "?";
      }
    }
    out.year = convertYear(f.year, src, tgt);

    const text = tgt.fields
      .map((n) => out[n])
      .filter((v) => v !== null)
      .join(" ");
    const warn = intervalWarning(f, tgt);
    if (warn) warnings.push(warn);
    return { expression: text, warnings };
  }

  function convert(expr, fromId, toId) {
    const parsed = parse(expr, fromId);
    if (!parsed.ok) return { ok: false, error: parsed.error };
    const src = getFlavour(fromId);
    const tgt = getFlavour(toId);
    if (fromId === toId) return { ok: true, expression: trimAscii(String(expr)), warnings: [] };
    try {
      const { expression, warnings } = convertCron(parsed.cron, src, tgt);
      const wrapped = tgt.id === "aws" && !expression.startsWith("@") ? "cron(" + expression + ")" : expression;
      const check = parse(wrapped, toId);
      if (!check.ok) throw new Error("convert produced an invalid " + tgt.label + " expression: " + check.error);
      return { ok: true, expression: wrapped, warnings };
    } catch (e) {
      if (e instanceof ConvertRefusal) return { ok: false, error: e.message };
      throw e;
    }
  }

  // What the page should do when the flavour select changes.
  //   empty: nothing typed; reparse: the text isn't valid in `fromId`, so there is nothing to
  //   preserve and the page just revalidates it under `toId`; converted / refused as convert().
  function switchFlavour(expr, fromId, toId) {
    if (trimAscii(String(expr)) === "") return { action: "empty" };
    if (!parse(expr, fromId).ok) return { action: "reparse" };
    const res = convert(expr, fromId, toId);
    if (!res.ok) return { action: "refused", error: res.error };
    return { action: "converted", expression: res.expression, warnings: res.warnings };
  }

  // ---- Builder model ------------------------------------------------------
  // Models use canonical values (dow 0-6, Sun=0); fromBuilder writes the flavour's own numbering.
  const fieldMin = (name, flavour) => (name === "dow" ? 0 : bounds(name, flavour)[0]);
  const fieldMax = (name, flavour) => naturalMax(name, flavour, bounds(name, flavour));
  const toNativeValue = (v, name, flavour) => (name === "dow" ? v + flavour.dowBase : v);

  // A single number or name as typed -> native number, or null.
  function nativeValue(tok, name, flavour) {
    if (/^[0-9]+$/.test(tok)) return Number(tok);
    const info = names(name, flavour);
    const i = info ? info.list.indexOf(tok.toUpperCase()) : -1;
    return i < 0 ? null : i + info.offset;
  }

  const modelValue = (tok, name, flavour) => {
    const v = nativeValue(tok, name, flavour);
    return v === null ? null : name === "dow" ? toCanonicalDow(v, flavour) : v;
  };

  function builderSpecial(sp) {
    switch (sp.type) {
      case "last":
        return { mode: "last", offset: sp.offset };
      case "lastWeekday":
        return { mode: "weekday", day: "L" };
      case "nearestWeekday":
        return { mode: "weekday", day: sp.day };
      case "lastDow":
        return { mode: "last", dow: sp.dow };
      default:
        return { mode: "nth", dow: sp.dow, nth: sp.nth };
    }
  }

  // "*/n", "a/n" or "a-max/n" -> step; null when it is some other shape.
  function builderStep(base, step, name, flavour) {
    if (base === "*") return { mode: "step", start: fieldMin(name, flavour), step };
    const parts = base.split("-");
    if (parts.length > 2) return null;
    if (parts.length === 2 && nativeValue(parts[1], name, flavour) !== fieldMax(name, flavour)) return null;
    const native = nativeValue(parts[0], name, flavour);
    if (native === null || native > fieldMax(name, flavour)) return null;
    return { mode: "step", start: modelValue(parts[0], name, flavour), step };
  }

  function classifyField(spec, name, flavour) {
    if (spec.question) return { mode: flavour.question === "alias" ? "every" : "none" };
    if (spec.special) return builderSpecial(spec.special);
    const raw = spec.raw;
    const custom = { mode: "custom", raw };
    if (raw === "*") return { mode: "every" };
    const items = raw.split(",");
    if (items.length === 1) {
      const m = /^([^/]+)\/([0-9]+)$/.exec(raw);
      if (m) {
        // Spring day-of-week steps start from Monday, which the model can't say: list the values.
        if (name === "dow" && flavour.monBasedDowSteps) return { mode: "specific", values: spec.values };
        return builderStep(m[1], Number(m[2]), name, flavour) || custom;
      }
      const parts = raw.split("-");
      if (parts.length === 2) {
        const from = modelValue(parts[0], name, flavour);
        const to = modelValue(parts[1], name, flavour);
        // A native 7 (Sunday) end folds to 0, which would change the range's meaning.
        const sevenEnd = name === "dow" && flavour.dowAllowsSeven && nativeValue(parts[1], name, flavour) === 7;
        return from === null || to === null || from > to || sevenEnd ? custom : { mode: "range", from, to };
      }
    }
    if (items.every((it) => nativeValue(it, name, flavour) !== null)) return { mode: "specific", values: spec.values };
    return custom;
  }

  // The flavour's fields as BuilderFields; null for @reboot.
  function toBuilder(cron) {
    if (cron.reboot) return null;
    const flavour = getFlavour(cron.flavour);
    const out = {};
    for (const n of flavour.fields) out[n] = classifyField(cron.fields[n], n, flavour);
    return out;
  }

  function builderFieldText(b, name, flavour) {
    const num = (v) => toNativeValue(v, name, flavour);
    switch (b.mode) {
      case "every":
        return "*";
      case "none":
        return "?";
      case "step": {
        if (name === "dow" && flavour.monBasedDowSteps) {
          return range(b.start, 6, b.step).map(num).join(",");
        }
        if (b.start === fieldMin(name, flavour)) return "*/" + b.step;
        // Unix and GitHub reject "a/n"; they need the explicit end of the range.
        const end = flavour.question === "none" ? "-" + fieldMax(name, flavour) : "";
        return num(b.start) + end + "/" + b.step;
      }
      case "specific": {
        const vals = [...new Set(b.values)].sort((x, y) => x - y);
        if (vals.length === 0) throw new Error("Choose at least one " + FIELD_LABELS[name] + " value.");
        return vals.map(num).join(",");
      }
      case "range":
        return num(b.from) + "-" + num(b.to);
      case "last":
        if (name === "dow") return num(b.dow) + "L";
        return b.offset ? "L-" + b.offset : "L";
      case "weekday":
        return b.day === "L" ? "LW" : b.day + "W";
      case "nth":
        return num(b.dow) + "#" + b.nth;
      case "custom":
        return b.raw;
      default:
        throw new Error("Unknown builder mode: " + b.mode);
    }
  }

  function fromBuilder(builder, flavourId) {
    const flavour = getFlavour(flavourId);
    const parts = [];
    for (const n of flavour.fields) {
      const b = builder[n] || { mode: "every" };
      if (n === "year" && flavour.optionalYear && b.mode === "every") continue;
      parts.push(builderFieldText(b, n, flavour));
    }
    return parts.join(" ");
  }

  // Modes the UI may offer for a field, in display order.
  function builderModes(fieldName, flavourId) {
    const flavour = getFlavour(flavourId);
    const modes = ["every", "step", "specific", "range"];
    const day = fieldName === "dom" || fieldName === "dow";
    if (day && flavour.question === "required") modes.push("none");
    if (day && flavour.specials) modes.push("last", fieldName === "dom" ? "weekday" : "nth");
    modes.push("custom");
    return modes;
  }

  return { FLAVOURS, getFlavour, parse, nextRuns, explain, convert, switchFlavour, toBuilder, fromBuilder, builderModes };
});
