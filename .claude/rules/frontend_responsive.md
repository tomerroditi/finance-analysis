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
- Padding: `p-4 md:p-8` (reduced on mobile)
- Mobile top bar offset: `pt-14 md:pt-0`

## Responsive Breakpoint Strategy

**Mobile-first** — write base styles for mobile, add `sm:`, `md:`, `lg:` for larger screens.

| Breakpoint | Width | Use for |
|---|---|---|
| (base) | < 640px | Phone portrait — single column, compact spacing |
| `sm:` | ≥ 640px | Phone landscape / small tablet — 2-column grids |
| `md:` | ≥ 768px | Tablet — sidebar visible, desktop-like padding |
| `lg:` | ≥ 1024px | Desktop — multi-column layouts, side-by-side panels |

## Required Patterns

### Spacing & Padding
Always use responsive variants for container padding:
```
p-4 md:p-6        (cards, modals)
p-4 md:p-8        (page content)
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

### Hover-Only Interactions
**Critical:** `hover:` states don't work on touch devices. Any UI that relies on hover to reveal actions (edit, delete buttons) MUST be visible by default on mobile:
```
opacity-100 md:opacity-0 group-hover:opacity-100
```

### Floating Bars / Fixed Position Elements
Floating action bars (bulk actions, FABs) must:
- Use `inset-x-4` on mobile (not centered with `left-1/2 -translate-x-1/2`)
- Have solid opaque backgrounds with `backdrop-blur-xl` and strong shadows
- Account for mobile bottom navigation: `bottom-4 md:bottom-8`

### Charts (Plotly)
- `plotlyConfig()` already sets `responsive: true` — charts auto-resize
- Use `style={{ width: "100%", height: "100%" }}` with `useResizeHandler`
- Prefer horizontal legends (`orientation: "h"`) over vertical — they fit mobile better
- Reduce chart margins on mobile: `margin: { l: 80, r: 20 }` instead of large values
- Container height: use `min-h-[400px] md:h-[600px]` so charts can expand on mobile

### Sidebar Panels (e.g., AutoTaggingPanel)
Desktop sticky panels don't work on mobile. Pattern:
- Desktop: `hidden md:flex` sticky side panel
- Mobile: Floating action button (FAB) + full-screen bottom sheet overlay

## Mobile Infrastructure

### Viewport & Meta Tags (`index.html`)
- `viewport-fit=cover` enables safe area support for notched devices
- `theme-color` matches `--background` for native-like status bar
- `apple-mobile-web-app-capable` + `black-translucent` status bar style

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

## Anti-Patterns (Do NOT)

- `flex-1` on tab buttons without `sm:` prefix — causes squishing instead of scrolling
- `whitespace-nowrap` without `overflow-x-auto` on parent — causes clipping
- Fixed `h-[Npx]` on containers with variable content — use `min-h-[Npx]` on mobile
- `opacity-0 group-hover:opacity-100` without mobile fallback — buttons invisible on touch
- Physical `left`/`right` properties — use logical `start`/`end` (RTL compatibility)
- Large fixed margins (`margin: { l: 100, r: 200 }`) on charts — clips on narrow screens
- `h-screen` / `100vh` on mobile-visible elements — use `h-dvh` / `100dvh` instead
- Inputs with `text-xs` / `text-sm` without the global iOS zoom fix — will cause unwanted zoom
