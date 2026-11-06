---
name: argus-brand
description: Argus brand and colour rules. Use when working on the Argus frontend UI, logo or favicon, colours, theming (light/dark), or any styling: which logo file to use and how, the colour tokens in tokens.css, the gain-vs-brand green rule, and component state colours.
---

# Argus brand (v1, 2026-11-07)

Argus is a single-user, data-dense swing-trading dashboard (Portfolio, Watchlist, Reports, Fund Manager, Themes, Runs), used mostly at night and pre-market. **Dark theme is the default.** This skill folder is self-contained; copy it to the Argus repo as `.cursor/skills/argus-brand/`.

## Files
| File | Use |
|---|---|
| `assets/logo/lockup-dark.svg` / `lockup-light.svg` | Mark + "Argus" wordmark (text outlined, no font needed). Header / about / docs. |
| `assets/logo/mark-dark.svg` / `mark-light.svg` | Standalone mark. Collapsed sidebar, loading state, avatars. |
| `assets/logo/favicon.svg` | Adaptive favicon (switches with `prefers-color-scheme`). Preferred. |
| `assets/logo/favicon.ico`, `favicon-16.png`, `favicon-32.png` | Fallbacks (light-mode artwork). `favicon-dark-16/32.png` for dark-only contexts. |
| `assets/logo/apple-touch-icon-180.png`, `icon-512.png` | Home-screen / PWA icons (dark tile `#0B0F17`, mark at ~68%). |
| `tokens.css` | CSS custom properties (`--argus-*`) for both themes + colour-blind palette. |
| `palette.json` | Source of truth for every colour (tokens.css is generated from it), incl. computed contrast for every pair. |
| `PALETTE.md` | Colour families, roles and rules (one page). |
| `contrast.md` | WCAG contrast table for all token pairs, both themes + colour-blind mode (0 failures). |

Favicon markup:
```html
<link rel="icon" href="/assets/logo/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/assets/logo/favicon.ico" sizes="16x16 32x32">
<link rel="apple-touch-icon" href="/assets/logo/apple-touch-icon-180.png">
```

## The logo: "Chart A", emerald
An "A" whose left leg is a rising price line, with a watchful dot (the eye of Argus) inside the A. Emerald mark + slate/white eye dot.

- **Pick the file by background, not by app theme toggle alone**: `*-light.svg` on light surfaces (emerald `#059669`, eye `#0F172A`), `*-dark.svg` on dark surfaces (emerald `#34D399`, eye `#F8FAFC`). In the app header, swap with `[data-theme]` (two `<img>`s toggled by CSS, or inline SVG using `currentColor` mapped to tokens).
- **Clear space**: keep empty space around the logo of at least **¼ of the mark height** (16 units on the 64-unit grid; 6px at a 24px header logo). No text, icons or borders inside it.
- **Minimum sizes**: lockup **24px tall** (wordmark stays legible); standalone mark **20px** in UI; **16px** only for favicons (use the provided PNG/SVG, don't rescale the lockup).
- **Header default**: lockup at 24–28px tall, left-aligned, vertically centred in the top bar.
- **Don't**:
  - stretch, skew, rotate, outline, add shadows/glows or gradients;
  - recolour the mark (no gain/loss colours, no red, no theme-random colours) or swap the eye dot colour;
  - place the light version on dark backgrounds or vice versa; place it on busy charts/photos;
  - rebuild the wordmark with a live font, change its tracking, or rearrange mark and wordmark;
  - use the lockup below 24px tall, or the mark alone as a decorative bullet;
  - animate the line/dot except a subtle loading pulse on the dot (≤ 1.2s, respect `prefers-reduced-motion`).

## Colour tokens
Use **only `var(--argus-*)` tokens** in components; never hard-code hex. Set the theme on `<html>`:
```html
<link rel="stylesheet" href="tokens.css">
<html data-theme="dark">              <!-- default; "light" also available; omit to follow the OS -->
<html data-theme="dark" data-palette="cvd">   <!-- opt-in colour-blind gain/loss (blue up / orange down) -->
```
| Role | Tokens |
|---|---|
| Page / panels | `--argus-bg` (page), `--argus-surface` (cards, tables), `--argus-surface-2` (headers, insets), `--argus-surface-hover`, `--argus-surface-selected` |
| Lines | `--argus-border` (dividers, table grid), `--argus-border-strong` (inputs, emphasis) |
| Text | `--argus-text` (primary, numbers), `--argus-text-2` (labels, secondary), `--argus-text-3` (meta, timestamps), `--argus-text-disabled` |
| Brand | `--argus-brand` (logo-adjacent accents, active tab indicator, graphics ≥3:1), `--argus-brand-text` (brand-coloured text/links), `--argus-brand-solid` + `--argus-on-brand` (primary button), `--argus-brand-subtle` (selected row/tab tint), `--argus-focus-ring` |
| Market direction | `--argus-gain`, `--argus-loss`, `--argus-flat` (+ `-subtle` backgrounds) |
| Status | `--argus-warn`, `--argus-info`, `--argus-danger`, `--argus-ok` (each + `-subtle`, `-border`) |
| Accent | `--argus-accent`, `--argus-accent-subtle` (violet: secondary highlights such as theme/AI tags; never data direction) |
| Buttons | `--argus-btn-{primary,secondary,ghost,danger}-{bg,hover,active,text}`, `--argus-btn-secondary-border`, `--argus-btn-disabled-{bg,border}` |
| Inputs | `--argus-input-{bg,border,border-hover,border-focus,disabled-bg,placeholder}` (invalid = `--argus-danger` border) |
| Ratings | `--argus-gain`/`--argus-on-gain`, `--argus-loss`/`--argus-on-loss`, `--argus-flat-subtle` (see state rules) |
| Charts | `--argus-chart-1…8` categorical series (no brand/gain/loss hues), `--argus-chart-grid`, `--argus-chart-axis` |
| Raw scales | `--argus-{emerald,violet,slate,lime,red,amber,sky,blue,orange}-*` (only for building new semantic tokens, not in components) |

Contrast: every text token pair meets WCAG AA (≥4.5:1) and every border/graphic/chart token ≥3:1 (see `contrast.md`). Light-theme `--argus-brand` (#059669) is 3.77:1 on white, so it is **for graphics/indicators only**; use `--argus-brand-text` (#047857, 5.48:1) for brand-coloured text. See `contrast.md`.

## Gain vs brand rule (important)
The brand is green, and so is "up" in markets. They must never be confused:
1. **Brand emerald never encodes data.** It is for identity and interaction (logo, active tab, primary button, focus, selection). Never colour a number, % change, P&L, candle or chart series with `--argus-brand*`.
2. **Gain is a different green**: lime-leaning (`#4D7C0F` light / `#A3E635` dark), hue ~85° vs emerald ~160°. Loss is red (`#C62828` / `#F87171`). Unchanged is `--argus-flat`.
3. **Colour is never the only signal** (WCAG 1.4.1): every change shows a sign and arrow, e.g. `+2.4% ▲`, `−1.8% ▼`, `0.0% ■`. Use a real minus `−` (U+2212).
4. **Colour-blind mode** (`data-palette="cvd"`) swaps gain/loss to blue/orange; components must only read the tokens so this works for free. Warn (amber) keeps its icon (⚠) to stay distinct from orange loss.
5. Primary buttons are emerald, so **never put a "Buy" or "Sell" action on the brand colour**: trade actions use neutral buttons with explicit labels; destructive/paid actions (e.g. start a paid run) use the confirm pattern with `--argus-danger`/`--argus-warn`.

## Component state rules (colour)
- **Default**: `--argus-surface` background, `--argus-border` border, `--argus-text` text.
- **Buttons**: four variants (primary = emerald solid, secondary = bordered surface, ghost = text only, danger = red solid), each with default / hover / active / focus / disabled / loading, all from `--argus-btn-*`. Loading keeps the label, adds a spinner and `aria-busy`, blocks clicks. Only one primary button per view.
- **Hover**: background `--argus-surface-hover`; don't change text colour or border width (no layout shift).
- **Focus (keyboard)**: always visible: 2px `--argus-focus-ring` outline, 2px offset (`:focus-visible`, already in tokens.css). Never remove outlines without a replacement.
- **Active / pressed**: one step darker in light (`--argus-brand-solid-hover` for primary), one step lighter in dark.
- **Selected** (tab, row, filter chip): `--argus-brand-subtle` background + a 2px `--argus-brand` indicator (underline for tabs, left bar for rows). Not colour alone: also `aria-selected`/`aria-current`.
- **Disabled**: `--argus-text-disabled` text, no hover, `cursor: not-allowed`, `aria-disabled`; keep borders visible.
- **Loading / stale data**: skeleton in `--argus-surface-2`; stale values (older than the last close) get `--argus-text-3` plus a "stale" badge in `--argus-warn`, never hidden.
- **Error / invalid input**: `--argus-danger` border + message below the field; alerts use `--argus-danger-subtle` bg + `--argus-danger-border`, with icon and written message.
- **Ratings** (Buy / Overweight / Hold / Underweight / Sell): Buy and Overweight use gain tokens, Hold uses flat, Underweight and Sell use loss tokens. Always print the word; strong ratings (Buy, Sell) use a solid `-subtle` fill, the moderate ones an outline.

## Typography, spacing, components — TBD (design system phase 2)
Not decided yet. Until then: Inter for UI text, JetBrains Mono for code/logs, `font-variant-numeric: tabular-nums` on every number, numbers right-aligned in tables. A full type scale, 4px spacing scale, radii, shadows, motion and component specs will be added in phase 2. Don't invent conflicting tokens; add new ones to `palette.json`/`tokens.css` with the `--argus-` prefix.
