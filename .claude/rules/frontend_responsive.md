---
paths:
  - "frontend/src/**/*.{ts,tsx}"
---

# Frontend Responsive Design - Mobile/Desktop Compatibility

## Layout Architecture

### Sidebar & Navigation
- **Desktop (`md:` and up):** Fixed sidebar (`hidden md:block`), collapsible between `w-64` (open) and `w-20` (icons). Main content uses `md:ms-64` / `md:ms-20` margin.
- **Mobile (below `md:`):** Sidebar hidden. Top bar (`h-14`, `z-40`) with hamburger menu + page title. Sidebar opens as a full-screen overlay drawer (`z-50`) with backdrop.
- **State:** `mobileSidebarOpen` in `appStore` controls the mobile drawer. Nav links call `setMobileSidebarOpen(false)` on click to auto-close.

### Main Content
- Padding: `p-2 sm:p-4 md:p-8` (tighter on mobile to maximize screen real estate)
- Mobile top bar offset: `pt-14 md:pt-0`

## Responsive Breakpoint Strategy

**Mobile-first** — write base styles for mobile, add `sm:`, `md:`, `lg:` for larger screens.

| Breakpoint | Width | Use for |
|---|---|---|
| (base) | < 640px | Phone portrait — single column, compact spacing |
| `sm:` | ≥ 640px | Phone landscape / small tablet — 2-column grids |
| `md:` | ≥ 768px | Tablet — sidebar visible, desktop-like padding |
| `lg:` | ≥ 1024px | Desktop — multi-column layouts, side-by-side panels |

## Desktop vs Mobile Design Patterns

### Action Buttons: Hover-Reveal (Desktop) vs Tap-Reveal (Mobile)

**The core UX difference:** Desktop uses hover to reveal contextual actions. Mobile has no hover — use **tap-to-reveal** action bars instead.

#### Pattern 1: Always-Visible on Dedicated Row (Budget rules, categories)
For items where actions are always relevant (edit/delete on budget rules, categories):
```tsx
{/* Desktop: inline, hidden until hover */}
{actions && (
  <div className="hidden md:flex opacity-0 group-hover:opacity-100 transition-opacity items-center gap-1">
    {actions}
  </div>
)}

{/* Mobile: dedicated row, always visible */}
{actions && (
  <div className="md:hidden flex items-center gap-1 mt-1.5">
    {actions}
  </div>
)}
```

#### Pattern 2: Tap-to-Reveal Action Card (Transaction lists, pending refunds)
For lists where showing all buttons inline would be too noisy:
```tsx
const [mobileActionsTxKey, setMobileActionsTxKey] = useState<string | null>(null);

{/* Row — tappable on mobile */}
<div
  className={`... sm:cursor-default cursor-pointer ${mobileActionsTxKey === txKey ? "bg-[var(--surface-light)]/30" : ""}`}
  onClick={() => {
    if (window.innerWidth < 640) {
      setMobileActionsTxKey(mobileActionsTxKey === txKey ? null : txKey);
    }
  }}
>
  {/* Desktop inline buttons */}
  <div className="hidden sm:grid ...">
    {/* action buttons */}
  </div>
</div>

{/* Mobile action card — slides in below tapped row */}
{mobileActionsTxKey === txKey && (
  <div className="sm:hidden flex items-center gap-1 mx-2 mb-1 ms-9 p-1.5 rounded-lg bg-[var(--surface-light)]/40 border border-[var(--surface-light)] animate-in fade-in slide-in-from-top-1 duration-150">
    <button onClick={(e) => { e.stopPropagation(); /* action */ }}>
      <Icon size={14} /> {t("label")}
    </button>
    {/* more action buttons with labels */}
  </div>
)}
```

**Key rules for tap-to-reveal:**
- Use `e.stopPropagation()` on action button clicks to prevent toggling the card
- Highlight the active row with a subtle background change
- Label buttons with text (not just icons) — mobile users need clarity
- Tapping another row should move the card, tapping the same row dismisses it

### Tables: Layout & Alignment

**The default `<table>` will squish itself to fit the viewport — on mobile that means headers collide ("BALANCEDEPOSITSWITHDRAWALS"), date cells wrap mid-token ("2026-/02-28"), badges and action buttons get clipped at the edge.** Force horizontal scroll instead:

```tsx
<div className="overflow-x-auto -mx-4 md:mx-0">
  <table className="w-full min-w-[640px] text-sm">
    <thead>
      <tr className="text-[10px] uppercase tracking-widest text-[var(--text-muted)] border-b border-[var(--surface-light)]">
        <th className="text-start  px-3 py-2 font-bold whitespace-nowrap">{t("common.date")}</th>
        <th className="text-center px-3 py-2 font-bold whitespace-nowrap">{t("investments.balance")}</th>
        <th className="text-center px-3 py-2 font-bold whitespace-nowrap">{t("investments.profit")}</th>
        <th className="text-center px-3 py-2 font-bold w-px"></th>{/* actions: collapse to content */}
      </tr>
    </thead>
    <tbody>
      {rows.map((row) => (
        <tr key={row.key} className="border-b border-[var(--surface-light)]/50 hover:bg-[var(--surface-light)]/30">
          <td className="text-start  px-3 py-2 whitespace-nowrap">{row.date}</td>
          <td className="text-center px-3 py-2 whitespace-nowrap">
            <span dir="ltr">{formatCurrency(row.balance)}</span>
          </td>
          <td className="text-center px-3 py-2 whitespace-nowrap">…</td>
          <td className="text-center px-3 py-2 whitespace-nowrap">{actionButtons}</td>
        </tr>
      ))}
    </tbody>
  </table>
</div>
```

**Required pattern:**
- **Wrap in `overflow-x-auto`** with `-mx-4 md:mx-0` so the scroll area extends to card edges on mobile.
- **Set `min-w-[640px]`** (or whatever the table needs) so columns can't squish below readability — the wrapper scrolls instead.
- **Every `<th>` and `<td>` must have `px-3 py-2`** — no padding = headers/cells run into each other.
- **Every cell needs `whitespace-nowrap`** — dates, currency, badges, and action buttons must not wrap or get truncated mid-content. If a cell genuinely needs to wrap (long descriptions), opt out explicitly.
- **Match alignment between `<th>` and `<td>`** — mixing `text-end` cells with `text-center` headers makes columns look misaligned. Pick one per column and apply it to both.
  - Numeric columns (currency, percentages): `text-center` in both header and cell.
  - Date / identifier columns: `text-start`.
  - Action / button columns: `text-center` and `w-px` to collapse to content width.
- **Wrap currency/numbers in `dir="ltr"`** so the shekel sign and minus stay in the right place under RTL.
- **Use `formatCurrency()`** (never `Intl.NumberFormat` inline) so RTL/locale handling is consistent.

### Tables: Mobile Column Trimming
- **Checkbox columns:** Hide on mobile with `hidden md:table-cell` — row tap already toggles selection with visual highlight, saving ~50px of horizontal space.
- **Column order:** Most important data (date, description, amount) appears first; less critical columns (account, source) come last so horizontal scroll on mobile shows the important columns first.
- **Source/badge columns** are often noise on mobile — consider whether they earn their column or whether the value can move into the row's primary cell or be removed entirely.

### Tooltips: Hover (Desktop) vs Tap-to-Toggle (Mobile)
Hover tooltips (`hidden group-hover:block`) don't work on touch. Use tap-to-toggle:
```tsx
function InfoTooltip({ text }: { text: string }) {
  const [show, setShow] = useState(false);
  return (
    <span className="group relative">
      <Info size={12} onClick={(e) => { e.stopPropagation(); setShow(v => !v); }} />
      <span className={`absolute ... max-w-[calc(100vw-3rem)] ${show ? "block" : "hidden group-hover:block"}`}>
        {text}
      </span>
      {show && <div className="fixed inset-0 z-[9]" onClick={() => setShow(false)} />}
    </span>
  );
}
```

### Dropdowns & Floating Panels
All dropdowns that use `createPortal` or `absolute` positioning MUST:
1. **Enforce minimum width:** `Math.max(rect.width, minWidth)` — at least 220px for multi-selects, 260px for create forms
2. **Clamp to viewport:** `Math.min(width, window.innerWidth - 16)` and `Math.max(8, left)`
3. **Fixed-width popovers:** Use `w-full max-w-[calc(100vw-2rem)] sm:max-w-80` instead of `w-80`

### Charts (Plotly)
- `plotlyConfig()` sets `responsive: true` — charts auto-resize
- Use `style={{ width: "100%", height: "100%" }}` with `useResizeHandler`
- **Legends:** Always horizontal (`orientation: "h"`). Default in `chartTheme`: `font: { size: 11 }, itemwidth: 30` — packs items into rows to save vertical space
- **Hover:** `chartTheme` uses `hovermode: "closest"` on touch devices (vs `"x unified"` on desktop). On touch, tapping a different point moves the tooltip; tapping empty area dismisses it. For charts that override hovermode, use: `hovermode: isTouchDevice ? "closest" : "y unified"`
- Reduce chart margins: `margin: { l: 80, r: 20 }` instead of large values
- Container height: use `min-h-[400px] md:h-[600px]`

## Required Patterns

### Spacing & Padding
Always use responsive variants for container padding:
```
p-4 md:p-6        (cards, modals)
p-2 sm:p-4 md:p-8 (page content — via Layout.tsx)
gap-2 md:gap-3    (tight grids)
gap-3 md:gap-6    (section grids)
space-y-4 md:space-y-6  (vertical stacks)
```

### Text Sizing
```
text-2xl md:text-3xl    (page titles)
text-lg md:text-xl      (section headings)
text-xs md:text-sm      (tab buttons, labels)
text-[10px] sm:text-xs  (KPI labels on small cards)
```

### Grids
Always start with mobile-first column count:
```
grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4    (stat cards)
grid grid-cols-1 lg:grid-cols-2                     (side-by-side panels)
grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6      (KPI strips)
grid grid-cols-1 sm:grid-cols-2                     (form fields in modals)
```

### Tab Bars & Button Groups
Tab bars MUST scroll horizontally on mobile instead of squishing:
```tsx
<div className="flex overflow-x-auto scrollbar-auto-hide gap-1">
  <button className="sm:flex-1 shrink-0 whitespace-nowrap px-2 md:px-3 ...">
```
- Use `sm:flex-1` (NOT `flex-1`) so tabs keep natural width on mobile
- Always add `shrink-0` and `whitespace-nowrap` on tab buttons
- Container needs `overflow-x-auto scrollbar-auto-hide`
- Scroll-snap is applied automatically via CSS on mobile

### Flex Layouts
Headers and control rows that overflow on mobile should stack:
```
flex flex-col md:flex-row md:items-center gap-3
```

### Fixed Widths
Avoid fixed widths on mobile. Use responsive variants:
```
w-full md:w-64      (dropdowns, selectors)
w-full md:w-auto    (button groups that should be full-width on mobile)
w-36 md:w-48        (month navigation labels)
```

### Modals
All modals must use this responsive container pattern:
```
w-full max-w-[calc(100vw-2rem)] sm:max-w-md    (small modals)
w-full max-w-[calc(100vw-2rem)] md:max-w-2xl   (large modals)
```
- Inner padding: `p-4 md:p-6`
- Form grids: `grid-cols-1 sm:grid-cols-2`
- Add `max-h-[90vh] flex flex-col` with `overflow-y-auto` on form body

### Floating Bars / Fixed Position Elements
Floating action bars (bulk actions, FABs) must:
- Use `inset-x-4` on mobile (not centered with `left-1/2 -translate-x-1/2`)
- Have solid opaque backgrounds with `backdrop-blur-xl` and strong shadows
- Account for mobile bottom navigation: `bottom-4 md:bottom-8`

### Sidebar Panels (e.g., AutoTaggingPanel)
Desktop sticky panels don't work on mobile. Pattern:
- Desktop: `hidden md:flex` sticky side panel
- Mobile: Floating action button (FAB) + full-screen bottom sheet overlay

### Touch Targets
Minimum 32px (preferably 44px) for tappable elements:
- Modal close buttons: `p-2` minimum (not `p-1`)
- Action icon buttons: `w-[32px] h-[32px]` minimum
- Inline rule actions: `p-2` with `size={16}` icons

## Mobile Infrastructure

### Viewport & Meta Tags (`index.html`)
- `viewport-fit=cover` enables safe area support for notched devices
- `theme-color` matches `--background` for native-like status bar
- `apple-mobile-web-app-capable` + `black-translucent` status bar style

### Global Touch CSS (`index.css`)
- `touch-action: manipulation` — eliminates 300ms tap delay on buttons/links/inputs
- `-webkit-tap-highlight-color` — subtle blue tap feedback instead of default gray
- `user-select: none` on buttons/nav — prevents accidental text selection
- `-webkit-touch-callout: none` on buttons — prevents long-press context menu
- `active:scale(0.97)` on touch devices (`@media (hover: none)`) — instant pressed feedback
- `scroll-snap-type: x proximity` on `.scrollbar-auto-hide` — tab bars snap on mobile
- `overscroll-behavior-y: contain` on body — prevents browser pull-to-refresh

### iOS Input Zoom Prevention (`index.css`)
iOS Safari auto-zooms when focusing inputs with `font-size < 16px`. Global CSS rule forces `font-size: 16px` on all inputs/selects/textareas below `md:` breakpoint.

### Safe Areas (`index.css`)
Body has `env(safe-area-inset-*)` padding for notched devices (iPhone X+, Dynamic Island). Requires `viewport-fit=cover` in the viewport meta tag.

### Dynamic Viewport Height
Use `h-dvh` instead of `h-screen` for full-height elements on mobile. `100dvh` accounts for the mobile browser address bar, `100vh` does not.
- Body: `min-height: 100dvh`
- Layout wrapper: `min-h-dvh`
- Mobile sidebar drawer: `h-dvh`

### Modal Scroll Lock
All modals/overlays MUST use the `useScrollLock(isOpen)` hook to prevent background scrolling on mobile:
```tsx
import { useScrollLock } from "../../hooks/useScrollLock";
// Inside component:
useScrollLock(isOpen);
```
Also add `modal-overlay` CSS class to the outermost `fixed inset-0` div for `overscroll-behavior: contain`.

### Chart Hover on Touch (`plotlyLocale.ts`)
`chartTheme.hovermode` switches to `"closest"` on touch devices automatically. For charts that override hovermode, import and use:
```tsx
import { isTouchDevice } from "../utils/plotlyLocale";
hovermode: isTouchDevice ? "closest" : "y unified",
```

## Anti-Patterns (Do NOT)

- `flex-1` on tab buttons without `sm:` prefix — causes squishing instead of scrolling
- `whitespace-nowrap` without `overflow-x-auto` on parent — causes clipping
- Fixed `h-[Npx]` on containers with variable content — use `min-h-[Npx]` on mobile
- `opacity-0 group-hover:opacity-100` without mobile fallback — buttons invisible on touch
- Physical `left`/`right` properties — use logical `start`/`end` (RTL compatibility)
- Large fixed margins (`margin: { l: 100, r: 200 }`) on charts — clips on narrow screens
- `h-screen` / `100vh` on mobile-visible elements — use `h-dvh` / `100dvh` instead
- Inputs with `text-xs` / `text-sm` without the global iOS zoom fix — will cause unwanted zoom
- `w-80` or other fixed widths on popover panels without `max-w-[calc(100vw-2rem)]` — overflows on small phones
- `hidden group-hover:block` on tooltips without tap-to-toggle fallback — inaccessible on touch
- Checkbox columns in tables on mobile — waste space when row tap already selects
- `<table className="w-full">` without `min-w-[…]` — columns squish on mobile, headers collide, dates wrap mid-token, badges/actions get clipped at the edge
- Table cells without `px-3` and `whitespace-nowrap` — adjacent column content touches and labels like "BALANCEDEPOSITS" run together
- Mixing `text-end` cells with `text-center` headers (or vice versa) — values look misaligned with their column header on narrow screens
- Currency/numbers in tables without a `dir="ltr"` wrapper — shekel sign and minus drift around in RTL
- Inline action buttons in lists on mobile without tap-to-reveal alternative — unreachable
