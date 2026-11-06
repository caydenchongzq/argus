---
name: argus-brand
description: Argus brand and design system. Use when working on the Argus frontend UI (any tab, component, layout or styling), the logo or favicon, colours and theming (light/dark, colour-blind mode), typography, spacing, density, number formatting, or when adding or changing CSS/HTML in the Argus dashboard.
---

# Argus brand & design system (v2, 2026-11-07)

Argus is a single-user, data-dense swing-trading dashboard (Portfolio, Watchlist, Reports, Fund Manager, Themes, Runs), used mostly at night and pre-market. **Dark theme is the default.** This skill folder is self-contained; copy it to the Argus repo as `.cursor/skills/argus-brand/`.

## Files
| File | Use |
|---|---|
| `assets/logo/lockup-dark.svg` / `lockup-light.svg` | Mark + "Argus" wordmark (text outlined, no font needed). Header / about / docs. |
| `assets/logo/mark-dark.svg` / `mark-light.svg` | Standalone mark. Collapsed sidebar, loading state, avatars. |
| `assets/logo/favicon.svg` | Adaptive favicon (switches with `prefers-color-scheme`). Preferred. |
| `assets/logo/favicon.ico`, `favicon-16.png`, `favicon-32.png` | Fallbacks (light-mode artwork). `favicon-dark-16/32.png` for dark-only contexts. |
| `assets/logo/apple-touch-icon-180.png`, `icon-512.png` | Home-screen / PWA icons (dark tile `#0B0F17`, mark at ~68%). |
| `tokens.css` | All design tokens (`--argus-*`): colours for both themes + colour-blind palette (palette v1.1, unchanged), plus phase-2 foundations: fonts, type scale, spacing, radii, borders, shadows, motion, z-index, layout, density. |
| `components.css` | Component classes (`.ar-*`), built only on tokens. Load after tokens.css. |
| `showcase.html` | Living reference of every component, with theme (Light/Dark/Auto) and density toggles. `?theme=light&density=compact` URL params. |
| `assets/icons/` | Vendored **Lucide v1.70.0** (ISC, `LICENSE`, `VERSION.txt`): `argus-icons.svg` sprite of the icons Argus uses (preferred, ~9KB) and the full `lucide.min.js` (481KB) for prototyping/`data-lucide`. No CDN. |
| `fonts/` | Self-hosted Inter + JetBrains Mono variable woff2 (Latin subset, SIL OFL 1.1, licences included). Loaded by tokens.css. |
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
- **Selected** (tab, row, filter chip): `--argus-brand-subtle` background + a brand indicator (2px underline for tabs, 3px left bar for table rows). Not colour alone: also `aria-selected`/`aria-current`.
- **Disabled**: `--argus-text-disabled` text, no hover, `cursor: not-allowed`, `aria-disabled`; keep borders visible.
- **Loading / stale data**: skeleton in `--argus-surface-2`; stale values (older than the last close) get `--argus-text-3` plus a "stale" badge in `--argus-warn`, never hidden.
- **Error / invalid input**: `--argus-danger` border + message below the field; alerts use `--argus-danger-subtle` bg + `--argus-danger-border`, with icon and written message.
- **Ratings** (Buy / Overweight / Hold / Underweight / Sell): Buy and Overweight use gain tokens, Hold uses flat, Underweight and Sell use loss tokens. Always print the word; strong ratings (Buy, Sell) use a solid `-subtle` fill, the moderate ones an outline.

## Design system (phase 2)

### Setup
```html
<html lang="en" data-theme="dark" data-density="comfortable">
<link rel="stylesheet" href="/static/argus-brand/tokens.css">     <!-- fonts/ must sit next to tokens.css -->
<link rel="stylesheet" href="/static/argus-brand/components.css">
<body class="ar-body">
```
Copy `tokens.css`, `components.css`, `fonts/` and `assets/` together. Open `showcase.html` for the reference implementation of everything below. Use the existing `.ar-*` classes before writing new CSS; new CSS must use only `var(--argus-*)` tokens (no raw hex, px font sizes or ad-hoc shadows).

### Typography
- **Inter** for all UI text and numbers; **JetBrains Mono** only for code, logs, file paths, IDs and JSON. Self-hosted from `fonts/` (no Google Fonts CDN).
- Every number gets **tabular figures** (`.ar-num` / `.ar-data`, or `font-variant-numeric: tabular-nums`). Tables and stat tiles already do this.

| Token / class | Size / line | Weight | Use |
|---|---|---|---|
| `display` `.ar-display` | 32 / 40 | 600, tight | rare: empty-dashboard hero, login |
| `h1` `.ar-h1` | 24 / 32 | 600, tight | page title (one per tab) |
| `h2` `.ar-h2` | 20 / 28 | 600 | major section |
| `h3` `.ar-h3` | 16 / 24 | 600 | dialog title, sub-section |
| `h4` `.ar-h4` / `.ar-card__title` | 12 / 16 | 600, CAPS +0.06em | card & section labels |
| `body-lg` | 14 / 22 | 400 | report prose (Reports tab) |
| `body` (default) | 13 / 20 (compact 12 / 18) | 400 | UI text, controls |
| `small` | 12 / 16 | 400 | meta, secondary lines |
| `caption` | 11 / 14 | 400–500 | column headers, timestamps, units |
| `data` `.ar-data` | 13 / 20 | 500, tnum | table numbers |
| `data-lg` `.ar-stat__value` | 24 / 32 | 600, tnum | stat tile value |
| `code` | 12 / 18 | mono | logs, code, JSON |

Weights: 400 regular, 500 medium, 600 semibold (headings, buttons, key numbers), 700 rarely. In dark mode don't go heavier than the light-mode equivalent. Use sentence case everywhere except `h4` labels.

### Spacing, radii, borders, elevation
- **4px scale:** `--argus-space-1` 4 · `-2` 8 · `-3` 12 · `-4` 16 · `-5` 20 · `-6` 24 · `-8` 32 · `-10` 40 · `-12` 48 · `-16` 64 (+ `-0-5` 2, `-1-5` 6). No other values.
- Inside a component: 4–12. Between components in a card: 12–16. Between cards: `--argus-gap` (16, compact 12). Page padding: `--argus-page-pad` (24, compact 16).
- **Radii:** `xs` 3 (checkbox, kbd) · `sm` 4 (status badges, tooltip) · `md` 6 (buttons, inputs, tabs, code) · `lg` 10 (cards, alerts, tables, toasts) · `xl` 14 (dialogs) · `full` (rating pills, switches).
- **Borders:** 1px `--argus-border` for dividers and cards, `--argus-border-strong` for inputs/table header; 2px for selection indicators (`--argus-border-width-strong`). Focus is always a 2px `--argus-focus-ring` outline with 2px offset.
- **Elevation:** `shadow-sm` cards/tiles · `shadow-md` hover lift, dropdowns, tooltips · `shadow-lg` toasts · `shadow-overlay` dialogs. In dark mode, separation comes mainly from surface steps (`bg` → `surface` → `surface-2`) and borders; shadows are a secondary cue.

### Motion
- Durations: `instant` 80ms (hover colour) · `fast` 120ms (press, toggle) · `base` 180ms (tooltip, toast, tab indicator) · `slow` 280ms (dialog). Easing: `--argus-ease-standard` for state changes, `-enter` for things appearing, `-exit` for leaving.
- Animate opacity, colour and transform only (never layout/width/height of data). No motion on live numbers. Don't flash cells on price updates; at most a 1s background fade using the `-subtle` token.
- `prefers-reduced-motion: reduce` sets all durations to 0, stops skeleton shimmer and slows spinners. Never rely on motion to convey meaning.

### Z-index, breakpoints
- Z-index tokens only: `sticky` 10 (table header) · `header` 20 · `dropdown` 30 · `overlay` 40 · `modal` 50 · `toast` 60 · `tooltip` 70.
- Breakpoints: `sm` 640 · `md` 960 · `lg` 1280 · `xl` 1600. Argus is a desktop tool: design for 1440–1920 wide. At < 1280 the 12-col spans collapse (`span-3` → 6, others → 12); at < 960 the header meta hides. Don't build a separate mobile layout.

### Layout
- **App shell:** sticky `.ar-header` (52px): logo lockup (24–28px tall) → primary tabs (`.ar-tabs` with Portfolio · Watchlist · Reports · Fund Manager · Themes · Runs) → spacer → data timestamp (`.ar-header__meta`, always show "data as of …" with timezone) → actions (theme toggle, density, run button).
- **Content:** `.ar-main`, max-width `--argus-content-max` (1680px), centred, page padding by density. A page starts with `.ar-page-head` (h1 + one primary action), then a row of 3–4 stat tiles, then the main table/chart, then secondary cards.
- **Grid:** `.ar-grid` 12 columns with `.ar-span-{3,4,5,6,7,8,9,12}`. Common splits: 4 × span-3 tiles; 8 + 4 (table + alerts/side panel); 6 + 6; 4 + 4 + 4. `.ar-cards` auto-fills 240px-min cards for watchlist/theme grids.
- **Hierarchy:** the largest thing on screen is the key number (portfolio value), not a heading. One primary button per view. Filters live in the card header, not above the page.

### Density
- `data-density="comfortable"` (default): rows 36, controls 32, card padding 16, body 13px.
- `data-density="compact"`: rows 28, controls 28, card padding 12, body/data 12px, icons 14, secondary lines in ticker cells hidden. Use for the Watchlist (50+ rows) and Runs history; the user can switch globally (stored in `localStorage` as `argus-density`).
- Never mix densities inside one table. Don't shrink below compact; paginate or virtualise instead.

### Number formatting (mandatory)
- **Sign:** always show `+` for positive changes and a true minus `−` (U+2212) for negatives: `+1.29%`, `−$118.25`. Zero is `0.00%` with no sign. Levels (price, value, qty) have no `+`.
- **Arrows:** every change carries `▲` (up), `▼` (down) or `■` (flat) after the number, plus the gain/loss/flat colour (`.ar-delta--gain|loss|flat`). Colour never stands alone.
- **Decimals:** prices 2 dp (`181.60`); sub-$1 prices 4 dp (`0.8123`); FX rates 4 dp (5 for JPY crosses: 3); % change 2 dp in tables (`−1.84%`), 1 dp in tiles/charts (`+16.7%`), but keep 2 dp when |x| < 1 (`+0.38%`); weights 1 dp (`24.9%`); quantities integer (fractional: up to 4 dp, trailing zeros trimmed); ratios/beta 2 dp; ATR 2 dp.
- **Currency:** `$` before the number, sign before the `$` (`−$212.80`); thousands separators always (`$11,985.60`); full precision in tables, abbreviated on tiles and chart axes only when > 6 digits (`$1.25M`, `$48.2K`). Other currencies by ISO code suffix (`5,120.00 MYR`). One currency per column, stated in the header if not USD.
- **Percent:** no space before `%`; percentage-point changes as `pts` (`5.3 pts over cap`).
- **Missing / stale:** `—` (em dash) for no data, never `0` or blank; stale values in `--argus-text-3` with a `⚠ Stale` badge and the as-of date in a tooltip.
- **Dates & times:** `Fri 6 Nov` in UI, ISO `2026-11-06` in logs/exports; times 24h with zone label (`05:30 MYT`, `16:00 ET`). Market data is stamped with the US session date.
- **Alignment:** numbers right-aligned (`.ar-num`) in tables and numeric inputs (`.ar-input--num`); headers of numeric columns right-aligned too; text left. Units in the header (`Price (USD)`), not repeated in every cell (except `$` on money and `%` on percents).

### Components (all in `components.css`)
| Component | Classes | Rules |
|---|---|---|
| Button | `.ar-btn` + `--primary` / (secondary default) / `--ghost` / `--danger`; sizes `--sm` / md (default) / `--lg`; `--icon`, `--block`; `.ar-btn__icon` (`--trailing`), `.ar-btn__label`; `.ar-btn-group`, `--equal` | See **Buttons** below. |
| Input / select | `.ar-field` > `.ar-label` + `.ar-input` / `.ar-select` + `.ar-hint` / `.ar-error`; `.ar-input-group` for icon/suffix; `.ar-input--num` | Label always visible (no placeholder-only labels). Invalid = `aria-invalid="true"` + `.ar-error` text. |
| Checkbox / switch | `.ar-check`, `.ar-switch` (`role="switch"`) | Checkbox for selection/consent, switch for settings that apply immediately. |
| Segmented / theme toggle | `.ar-segmented` with `button[aria-pressed]` | Theme: Light / Dark / Auto(system), stored as `argus-theme`; default Dark. |
| Tabs | `.ar-tabs` (header) / `.ar-tabs--inline` (in-card); `.ar-tab[aria-selected]`, `.ar-tab__count` | Selected = brand underline + subtle tint. Max ~7 tabs. |
| Card | `.ar-card`, `__header`, `__title`, `__body`, `__footer`, `--flush`, `--interactive` | Title is an `h4`-style label; actions/filters right side of header. |
| Stat tile | `.ar-stat`, `__label`, `__value`, `__delta`, `__meta`, `--warn`; `.ar-meter` | Label → value → delta (signed, arrow, period) → meta. 3–4 per row. Breaches use `--warn` + meter with cap mark. |
| Table | `.ar-table-wrap` (`--ar-table-max-h` for sticky header scrolling), `.ar-table`, `.ar-num`, `.ar-ticker` (+ `small`), `th[aria-sort] > .ar-sort`, `tr[aria-selected]`, `tr.is-stale`, `--compact`, `--striped`, `tfoot` | Sticky header; sortable headers are buttons with `aria-sort`; hover tint; selected row = tint + 3px brand bar; default sort stated in footer or header. |
| Rating badge | `.ar-rating--buy|overweight|hold|underweight|sell` | Always the word. Solid for Buy/Sell, outlined for Overweight/Underweight. |
| Status badge | `.ar-badge--info|warn|ok|danger|neutral|accent`, `.ar-badge__dot` | Include an icon/glyph (✓ ⚠ ✕ ●) so status isn't colour-only. |
| Alert | `.ar-alert--info|warn|danger|ok` with icon, `__title`, `__body`, `__actions` | Inline, persistent conditions. `role="alert"` for errors, `role="status"` otherwise. |
| Toast | `.ar-toast-stack` (fixed bottom-right) > `.ar-toast--ok|warn|danger|info` | Transient confirmations (auto-dismiss 5s, errors stay until dismissed). `aria-live="polite"`. |
| Dialog / confirm | `dialog.ar-dialog` (or `role="alertdialog"`), `__header`, `__icon(--danger)`, `__title`, `__body`, `__summary` (dl), `__actions` | Required before any paid run, trade-plan apply or delete: show what/how many/estimated cost/market state, a consent checkbox for paid runs, Cancel (ghost) left of the confirm button. Esc closes, focus trapped, focus returns to trigger. |
| Tooltip | `[data-tooltip="…"]` (+ `tabindex="0"` on non-buttons), `.ar-info-dot` | Supplementary info only (never the only place a value lives). 300ms delay, inverted colours. |
| Code / log | `.ar-code` (`tok-key|str|num|com`), `.ar-log` > `.ar-log__line--info|warn|error|ok` with `__ts`, `__lvl`, `__msg` | Logs always dark (terminal style) in both themes; timestamps 24h. Never print secrets/API keys. |
| Empty / loading | `.ar-empty` (`__icon`, `__title`, `__text` + one action), `.ar-skeleton--text|value|row`, `.ar-spinner` | Empty states explain why and offer one next step. Skeletons mimic final layout; spinners only for < 2s or inline. |
| Icons | `.ar-icon` (`--sm` 14, `--lg` 20), `.ar-btn__icon` | See **Icons (Lucide)** below. |

### Buttons
- **Sizes:** `sm` 26px (compact 24) is **icon-only**: a square with no visible label. It **must** have `aria-label` and `data-tooltip` naming the action (put the name in a visually hidden `.ar-btn__label` too). `md` 32px (compact 28) and `lg` 38px (compact 34) are **icon + label**.
- **Widths:** md has `min-width: 96px` (compact 88), lg `120px` (compact 112), so short labels ("Run", "Export", "Cancel") render at the same width. The label is centred. Longer labels grow the button; keep labels to 1–3 words. Icon-only (`--sm`, `--icon`) stays square.
- **Equal widths:** wrap related buttons (dialog footers, toolbars) in `.ar-btn-group.ar-btn-group--equal` so every button takes the widest one's width. In narrow panels use `.ar-btn--block` (full width).
- **Icons:** a leading icon by default (`<i class="ar-btn__icon" data-lucide="play">` or a sprite `<svg class="ar-btn__icon">`). Trailing icon (`.ar-btn__icon--trailing`) only for menus/disclosure (`chevron-down`) or leaving the app (`external-link`). Icon size follows the button: sm 14, md 16, lg 18 (`--argus-btn-icon-*`). Gap is `--argus-btn-gap` (6px; lg 8px).
- **Loading:** set `aria-busy="true"` and change the label to the progressive form ("Running…"). The spinner **replaces the leading icon**; the width doesn't change; clicks are blocked.
- **Variants:** one primary per view; ghost for Cancel/tertiary actions; danger only for destructive actions; paid runs use primary inside the confirm dialog. Cancel sits left of the confirm button.
- **Recommended action icons:**

| Action | Lucide icon | Usual variant |
|---|---|---|
| Run / start analysis | `play` | primary |
| Refresh / refetch | `refresh-cw` | secondary or sm ghost |
| Confirm / apply | `check` | primary |
| Cancel / close / dismiss | `x` | ghost |
| Delete / remove | `trash-2` | danger |
| Export / download | `download` | secondary |
| Settings | `settings` | secondary or sm ghost |
| Search / filter | `search` / `filter` | in inputs / sm ghost |
| Copy | `copy` | sm ghost |
| Edit / save / import | `pencil` / `save` / `upload` | secondary |
| Open external | `external-link` (trailing) | ghost |
| Schedule / routine | `clock` / `calendar` / `bell` | secondary |

### Icons (Lucide)
- **Library:** Lucide **v1.70.0**, pinned and vendored in `assets/icons/` (ISC licence in `assets/icons/LICENSE`). No CDN, no runtime fetch. To upgrade: `npm pack lucide@X lucide-static@X`, replace `lucide.min.js`, regenerate the sprite, update `VERSION.txt`, re-check the showcase.
- **Production (preferred): SVG sprite.** Serve `assets/icons/argus-icons.svg` from the Argus server and reference icons by id:
  `<svg class="ar-icon" aria-hidden="true"><use href="/static/argus-brand/assets/icons/argus-icons.svg#refresh-cw"/></svg>`.
  The sprite holds only the icons in use (34). To add one, copy its `<symbol>` from lucide-static `icons/<name>.svg` (or add the name to `assets/icons/build_icons.py` and run it against an unpacked lucide-static). External `<use>` needs http(s); it won't load from `file://`.
- **Prototyping / showcase: `lucide.min.js`.** `<i class="ar-icon" data-lucide="play"></i>` + `<script src="assets/icons/lucide.min.js"></script><script>lucide.createIcons()</script>` (works offline and on `file://`). Classes on the `<i>` carry over to the generated `<svg>`.
- **Style:** 24-unit grid, stroke 2, `currentColor`, round caps. UI size 16px (`.ar-icon`), 14 in compact/`--sm`, 20 for empty states (`--lg`, stroke 1.75). Icons take the text colour of their context; don't colour icons with gain/loss unless they *are* the direction cue.
- **Accessibility:** decorative icons get `aria-hidden="true"`; icon-only controls need `aria-label` + tooltip. Never use an icon alone where a word is clearer (table cells, ratings).

### Do / don't
- **Do** keep the data the hero: big key numbers, quiet chrome, generous right-aligned numeric columns.
- **Do** show provenance: "data as of" timestamps, stale badges, cost estimates before paid actions.
- **Do** test every new screen in Dark, Light, compact density and `data-palette="cvd"`.
- **Don't** use brand emerald for data, put more than one primary button in a view, or use colour as the only signal.
- **Don't** hard-code colours/sizes, add new font families, use pure black/white surfaces, or round numbers differently from the rules above.
- **Don't** animate numbers, use full-screen spinners for partial loads, or hide errors in toasts that disappear.
