---
target: getip.html
total_score: 29
p0_count: 0
p1_count: 2
timestamp: 2026-07-12T19-43-17Z
slug: static-getip-html
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | "Not available" renders in the same muted gray as the loading state — hard to tell "still working" from "failed" at a glance |
| 2 | Match System / Real World | 3 | Terminology fits the stated technical audience, no unexplained jargon |
| 3 | User Control and Freedom | 3 | Clear back link, no traps; little to undo given read-only nature |
| 4 | Consistency and Standards | 3 | Implementation matches DESIGN.md tokens closely; one drift on `h1` weight |
| 5 | Error Prevention | 3 | N/A for most of the surface (no inputs); clipboard action isn't guarded |
| 6 | Recognition Rather Than Recall | 4 | Everything needed is visible on one screen |
| 7 | Flexibility and Efficiency | 3 | One-click copy is efficient; API-hint block serves power users |
| 8 | Aesthetic and Minimalist Design | 4 | Textbook minimal, one clear hierarchy |
| 9 | Error Recovery | 1 | "Not available" gives zero explanation, zero next step, at the moment most likely to actually trigger (client with no native IPv6) |
| 10 | Help and Documentation | 2 | No contextual help on geo fields; API-hint block partially substitutes |
| **Total** | | **29/40** | **Good — solid foundation, address weak areas (mainly #9 and #1)** |

## Anti-Patterns Verdict

**No, this doesn't read as AI-generated.** The generic tells (rounded cards, shadows, Inter/system-ui, gradient CTAs, purple/blue SaaS palette) are absent by deliberate, documented choice, and the implementation actually matches what DESIGN.md prescribes rather than just gesturing at it.

**Deterministic scan**: `detect.mjs` ran clean (no crash), exit code 2, 2 advisory findings — both rule `design-system-font-size`:
- `getip.html:65` — `.card-header h2` badge text at `0.65rem`, off DESIGN.md's documented ramp
- `getip.html:121` — `.unavailable` at `1.25rem`, also off-ramp

Both manually verified as true positives. Neither was caught by the design-review pass on its own.

**Browser visualization**: unavailable this run — no browser automation tool was exposed to either assessment agent.

## Overall Impression

A well-executed, quietly confident tool that mostly delivers on its own positioning. The gap is at the edges: the one interactive control (Copy IP) has a silent failure mode and a borderline-invisible resting state, and the one truly high-stakes moment (IPv6 unavailable) says nothing useful right when a real user is most likely to hit it.

## What's Working

1. Contrast is emphatic, not just adequate — IP value at 21:1, ink ramp clears WCAG AAA across the board.
2. Accessibility scaffolding is unusually thorough for a project this size, and done correctly.
3. The two `fetchIP()` calls run genuinely in parallel — behavior reinforces the "dual-stack, resolved independently" positioning.

## Priority Issues

**[P1] Clipboard copy fails silently, zero user feedback**
- Why it matters: only interactive control on the page; failure is invisible to the user.
- Fix: wrap `navigator.clipboard.writeText` in try/catch; show a distinct "Copy failed" state.
- Suggested command: `/impeccable harden`

**[P1] Copy button's resting border fails WCAG non-text contrast**
- Why it matters: `#555` border on `#000` ≈2.82:1, below the 3:1 minimum; PRODUCT.md names WCAG 2.1 AA as a formal target, and this is the button's entire visual definition at rest.
- Fix: brighten resting border to ≥`#5a5a5a`, or add a non-color cue.
- Suggested command: `/impeccable harden`

**[P2] Failure state is unclear, unexplained, and drifts off the type ramp**
- Why it matters: "Not available" gives no reason and is visually confusable with loading; detector independently flagged its font-size as off-ramp too.
- Fix: differentiate copy by likely cause, give it a distinct visual break, align font-size to a documented step.
- Suggested command: `/impeccable clarify`

**[P2] No responsive handling for the fixed footer**
- Why it matters: zero `@media` breakpoints exist; fixed footer holds attribution + 3-item nav in one unwrapped row, risking overlap on phone-width viewports.
- Fix: stack footer children vertically below a narrow-viewport breakpoint.
- Suggested command: `/impeccable layout`

**[P3] Small type-ramp drifts (bundled)**
- What: `h1` never sets `font-weight` (likely inherits bold UA default, contradicting the "only IP value is bold" rule); badge text at `0.65rem` and `.unavailable` at `1.25rem` both off-ramp.
- Fix: add explicit `font-weight: 400` to `h1`; move both sizes onto documented steps.
- Suggested command: `/impeccable typeset`

## Persona Red Flags

**Alex (Power User)**: Copy IP button isn't in the DOM until fetch resolves, so its position isn't stable across visits. Manual double-click selection of IPv6 text is unreliable (colons break word-boundary selection).

**Sam (Accessibility-Dependent)**: same border-contrast issue — hard to locate at low-vision magnification before hover/focus. Positive: screen-reader pass would go smoothly (skip link, 15.9:1 focus outline, correct aria-live/aria-busy). Minor: 2-column geo grid has no breakpoint, tight at 200% zoom.

## Minor Observations

- `border-faint` (`#1a1a1a`) computes to ≈1.2:1 against black — intentional "quiet divider" per DESIGN.md, not a bug.
- The API-hint `<code>` block serves the stated "friends who might script against it" audience well.
- No missing `rel="noopener"` anywhere.

## Questions to Consider

- Would the loading cursor and "Not available" state be the first honest place for the reserved retro accent to land, since they're the two spots where grayscale alone can't signal "this is different from normal"?
- If IPv6 failure is overwhelmingly "your network doesn't have it," should the copy ever say "not available," or should it say what it actually knows ("No IPv6 route detected")?
- Does a silent clipboard failure undercut the "precision" positioning more than a visibly broken feature would?
