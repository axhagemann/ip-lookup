---
name: ipinfo
description: A self-hosted, ad-free IPv4/IPv6 lookup tool with a quiet terminal aesthetic
colors:
  surface-bg: "#000000"
  ink-bright: "#ffffff"
  ink-primary: "#e0e0e0"
  ink-muted: "#c0c0c0"
  ink-soft: "#d0d0d0"
  border-faint: "#1a1a1a"
  border-subtle: "#1e1e1e"
  border-default: "#222222"
  border-strong: "#666666"
  border-hover: "#888888"
typography:
  value:
    fontFamily: "'Courier New', Courier, monospace"
    fontSize: "1.5rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "0.02em"
  label:
    fontFamily: "'Courier New', Courier, monospace"
    fontSize: "0.85rem"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "0.2em"
  body:
    fontFamily: "'Courier New', Courier, monospace"
    fontSize: "0.85rem"
    fontWeight: 400
    lineHeight: 1.7
    letterSpacing: "normal"
  caption:
    fontFamily: "'Courier New', Courier, monospace"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "0.1em"
rounded:
  none: "0px"
spacing:
  xs: "0.25rem"
  sm: "0.5rem"
  md: "1rem"
  lg: "1.5rem"
  xl: "2rem"
  2xl: "3rem"
components:
  button-copy:
    backgroundColor: "transparent"
    textColor: "{colors.ink-muted}"
    rounded: "{rounded.none}"
    padding: "0.25rem 0.65rem"
  button-copy-hover:
    backgroundColor: "transparent"
    textColor: "{colors.ink-primary}"
    rounded: "{rounded.none}"
    padding: "0.25rem 0.65rem"
  button-copy-copied:
    backgroundColor: "transparent"
    textColor: "{colors.ink-bright}"
    rounded: "{rounded.none}"
    padding: "0.25rem 0.65rem"
  card:
    backgroundColor: "{colors.surface-bg}"
    textColor: "{colors.ink-soft}"
    rounded: "{rounded.none}"
    padding: "1.5rem"
  badge:
    backgroundColor: "transparent"
    textColor: "{colors.ink-primary}"
    rounded: "{rounded.none}"
    padding: "0.15rem 0.45rem"
  tool-link:
    backgroundColor: "transparent"
    textColor: "{colors.ink-primary}"
    rounded: "{rounded.none}"
    padding: "1.25rem 1.5rem"
---

# Design System: ipinfo

## 1. Overview

**Creative North Star: "The Quiet Terminal"**

A console that only speaks when it has something precise to say. The system is pure black-on-gray monospace, built from borders instead of surfaces and silence instead of ornament — every screen reads like a `//`-commented terminal session rather than a product page. Density is low, contrast is high, and the only motion is a blinking cursor while data loads.

This explicitly rejects the ad-heavy "what's my ip" sites the project positions itself against: no banners, no gradient CTAs, no filler copy competing for attention. It also rejects generic SaaS chrome — no rounded cards, no shadows, no color for color's sake. Right now the palette is monochrome by choice, not by omission: a single retro-terminal accent (phosphor green or amber) is planned for a future pass but deliberately not yet introduced, so this system currently documents a grayscale-only state.

**Key Characteristics:**
- Pure black background, grayscale ink ramp, zero hue
- Square corners everywhere — no border-radius in the system
- Borders substitute for elevation; there are no shadows
- One monospace family end to end, no display/body pairing
- The `// ` prefix reads as a terminal comment marker, used on every heading

## 2. Colors

Strictly grayscale on black today — the system uses lightness alone to build hierarchy, with no hue anywhere in the interface.

### Neutral
- **Void Black** (`#000000`): the only background value in the system — body, cards, and buttons all sit directly on it.
- **Bright White** (`#ffffff`): reserved for the most important number on any screen (the resolved IP value) and for "confirmed" states like a copied button.
- **Primary Ink** (`#e0e0e0`): default text color — headings, nav links, primary copy.
- **Muted Ink** (`#c0c0c0`): secondary text — descriptions, uppercase labels, inactive links.
- **Soft Ink** (`#d0d0d0`): tertiary body copy inside cards (legal text, geo values).
- **Border Faint** (`#1a1a1a`): the quietest divider, used only under card headers.
- **Border Subtle** (`#1e1e1e`): legal-page card outline.
- **Border Default** (`#222222`): the standard card and tool-link outline.
- **Border Strong** (`#666666`): interactive borders at rest (buttons, inline `<code>`). Tuned up from an earlier `#555555` to clear the WCAG 3:1 non-text contrast minimum against pure black (`#555555` measured ≈2.82:1).
- **Border Hover** (`#888888`): the one-step-brighter state a border moves to on hover.

### Named Rules
**The No-Hue Rule.** Every color in this system is desaturated gray or pure black/white. Nothing is tinted toward warm or cool. If a color swatch has any chroma, it doesn't belong here — yet.

**The Reserved Accent Rule.** PRODUCT.md commits to exactly one future retro-terminal accent (phosphor green or amber), used sparingly (focus states, the loading cursor, one label). It does not exist in the codebase today. Do not introduce an accent color piecemeal — it lands as one deliberate decision, not a gradual creep.

## 3. Typography

**Display/Value Font:** "Courier New", Courier, monospace
**Body Font:** "Courier New", Courier, monospace
**Label/Mono Font:** "Courier New", Courier, monospace (the entire system is one family)

**Character:** A single monospace typeface carries every role — headings, body, labels, and data — so hierarchy comes entirely from size, weight, tracking, and case rather than a font pairing.

### Hierarchy
- **Value** (700, 1.5rem, line-height 1.2): the resolved IP address itself — the largest, brightest text on the page, and the only place bold white appears.
- **Heading/Label** (400, 0.85rem, line-height 1.4, letter-spacing 0.2em, uppercase): page titles, prefixed with `// `. Functions as both the page's h1 and a terminal-comment-style label — deliberately small and quiet rather than a hero display size.
- **Body** (400, 0.85rem, line-height 1.7): descriptions and explanatory copy, centered, capped near 520px measure.
- **Caption/Meta** (400, 0.75rem, line-height 1.6, letter-spacing 0.1em, uppercase): geo field labels, footer links, API hints — the smallest, quietest text in the system.

### Named Rules
**The Comment-Marker Rule.** Every heading is prefixed with `// ` (rendered `aria-hidden` so it doesn't pollute the accessible name). It's the one recurring typographic signature in the system — don't drop it, and don't add a second decorative prefix alongside it.

## 4. Elevation

There are no shadows anywhere in the system. Depth and grouping are conveyed entirely through 1px borders on a flat black field — a card is a rectangle with an outline, not a raised surface.

### Named Rules
**The Flat-By-Default Rule.** Surfaces never lift, blur, or cast shadow. If something needs to read as "grouped," give it a border (`border-default` or `border-subtle`); if it needs to read as "interactive," change the border color on hover/focus. Never add `box-shadow`.

## 5. Components

Buttons, cards, and badges all share one instinct: quiet and functional, no decoration beyond what a state requires.

### Buttons
- **Shape:** square corners, no radius (`0px`) — matches the system-wide no-rounding rule.
- **Primary (Copy IP):** transparent background, 1px `border-strong` (#666), `ink-muted` text, 0.25rem 0.65rem padding, 0.75rem monospace uppercase-free label.
- **Hover:** border shifts to `border-hover` (#888), text brightens to `ink-primary` (#e0e0e0). Transition on `border-color` and `color`, 0.1s.
- **Copied (confirmed state):** border and text both jump to `ink-bright` (#fff) — the only place a button turns fully white.
- **Failed (clipboard write rejected):** border switches to a dashed `border-hover` (#888) and text brightens to `ink-primary` (#e0e0e0) with the label reading "Copy failed" — distinct from the solid-white "Copied!" confirmation so success and failure are never confusable.

### Cards
- **Corner Style:** square (0px radius).
- **Background:** none — cards sit directly on `surface-bg` (#000); only the border differentiates them from the page.
- **Shadow Strategy:** none — see Elevation.
- **Border:** 1px `border-default` (getip lookup cards) or `border-subtle` (legal-page card); `border-faint` for the divider under a card's header.
- **Internal Padding:** 1.5rem (lookup cards), 2rem (legal-page card).

### Badges
- **Style:** inline-block, 1px border matching the ink color it names (`ink-primary` for IPv4, `ink-muted` for IPv6), 0.15rem 0.45rem padding, 0.75rem bold monospace (aligned to the Caption/Meta type step), no background fill.
- **State:** static — badges label a card, they don't have interactive states.

### Navigation / Links
- **Tool links (index page):** full-bleed 1px `border-default` block, `ink-primary` heading + `ink-muted` description inside; border brightens to `border-hover` on hover. No background change.
- **Footer links:** bare text, 0.75rem uppercase tracked, `ink-muted` at rest, `ink-bright` on hover, no underline, no border.
- **Back link:** same uppercase-tracked treatment as footer links, with an `aria-hidden` `← ` prefix mirroring the `// ` heading convention.

### Loading State (signature pattern)
While a value is in flight, its container gets a trailing blinking cursor (`::after { content: "_" }`, 1s step-end infinite) instead of a spinner — reinforcing the terminal metaphor. Disabled under `prefers-reduced-motion: reduce` in favor of a static cursor.

## 6. Do's and Don'ts

### Do:
- **Do** keep every corner square — `border-radius` is `0px` everywhere in this system, no exceptions.
- **Do** use borders, not shadows, for grouping and elevation.
- **Do** keep the `// ` (heading) and `← ` (back link) `aria-hidden` comment-marker prefixes when adding new pages.
- **Do** pair any new loading state with a `prefers-reduced-motion: reduce` fallback, matching the existing blinking-cursor pattern.
- **Do** treat the IP/value text as the one place bold white (`#ffffff`) appears — it should stay the brightest thing on any screen.

### Don't:
- **Don't** build ad-heavy "what's my ip" site patterns: no banner ads, no trackers, no SEO filler copy around the lookup.
- **Don't** introduce a rounded corner, a shadow, or a gradient anywhere — all three are absent by design, not by oversight.
- **Don't** add color piecemeal. The system is grayscale-only until the single reserved retro accent (phosphor green or amber) is introduced as one deliberate decision across the whole site.
- **Don't** pair a second display font with the existing monospace — the one-family system is the point, not a placeholder.
- **Don't** use a side-stripe border (`border-left`/`border-right` as a colored accent) — every border in this system is a full rectangle outline.
