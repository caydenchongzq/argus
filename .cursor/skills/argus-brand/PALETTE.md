# Argus colour palette v1.1 — Chart A emerald

Visual: `palette_sheet.png` in `argus-design/palette/`. Tokens: `tokens.css`. Contrast: `contrast.md` (80 pairs, 0 failures). 

## Colour families
| Role | Family | Light key value | Dark key value | Used for |
|---|---|---|---|---|
| Brand | emerald | `#059669` graphics, `#047857` text/buttons | `#34D399` | logo, primary button, active tab, selection, focus ring |
| Accent | violet | `#7C3AED` | `#A78BFA` | secondary highlights (theme / AI tags). Never data direction |
| Neutral | slate | `#0F172A` text · `#FFFFFF` surface · `#F8FAFC` bg | `#E2E8F0` text · `#121826` surface · `#0B0F17` bg | everything else |
| Gain | lime | `#4D7C0F` | `#A3E635` | up moves, Buy/Overweight |
| Loss | red | `#C62828` | `#F87171` | down moves, Sell/Underweight |
| Warn | amber | `#B45309` | `#FBBF24` | stale data, caps, earnings soon (always with ⚠) |
| Info | sky | `#0369A1` | `#38BDF8` | neutral notices, "live" |
| Danger | red | `#B91C1C` / solid `#DC2626` | `#F87171` | errors, destructive / paid actions |
| OK | emerald | `#047857` | `#34D399` | success messages (not data) |
| CVD gain/loss | blue / orange | `#2563EB` / `#C2410C` | `#60A5FA` / `#FB923C` | `data-palette="cvd"` |
| Chart series | sky, violet, amber, pink, teal, indigo, yellow, slate | `--argus-chart-1…8` | lighter set | categorical lines/bars. Excludes brand emerald, gain lime and loss red |

## Rules
1. **Brand green ≠ gain green.** Emerald (hue ~160°) is identity + interaction only; gain is lime (hue ~85°). Never colour data with brand tokens.
2. **Never colour alone:** `+2.4% ▲`, `−1.8% ▼`, `0.0% ■`; warnings carry ⚠, errors ✕, success ✓.
3. **Dark is the default theme**; light is the same tokens with different values. Components read only `var(--argus-*)`.
4. **Buttons:** primary (emerald solid), secondary (bordered surface), ghost (text), danger (red solid). States default / hover / active / focus / disabled / loading come from `--argus-btn-*`. Hover darkens in light and lightens in dark. Focus is always a 2px emerald ring with a 2px offset. Disabled uses neutral grey, not faded brand.
5. **Inputs:** border ≥3:1 (`--argus-input-border`), hover darker, focus emerald border + ring, invalid red border + message, disabled grey fill.
6. **Tables:** hover row `--argus-surface-hover`; selected row `--argus-surface-selected` + 3px emerald left bar; numbers right-aligned with tabular figures.
7. **Ratings:** Buy = solid gain, Overweight = outlined gain, Hold = neutral, Underweight = outlined loss, Sell = solid loss. The word is always printed.

## Known trade-offs
- Danger (destructive buttons) and loss share the red family; context (button vs number) and icons separate them.
- In CVD mode, orange loss sits near amber warn; warnings must keep the ⚠ icon.
- Lime gain is less conventional than pure green; switch to CVD mode if it feels off.
