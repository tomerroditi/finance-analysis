# Categories Page — Card Layout Redesign

**Date:** 2026-05-08
**Status:** Approved
**Scope:** Desktop layout of category cards in `frontend/src/pages/Categories.tsx`

## Problem

The current desktop layout has two issues:

1. **Hidden action buttons** — edit, add tag, and delete buttons are wrapped in `opacity-0 group-hover:opacity-100`, making them invisible until hover. This is a UX barrier; users can't discover or reach actions without accidentally hovering first.
2. **Buttons shift with name length** — action buttons are placed after the category name in a flex row, so their horizontal position varies per card. The list looks inconsistent and scanning actions across cards is visually noisy.

## Design

### Card row structure

Replace the current linear flex row with a **3-zone flex layout**:

```
| Left zone (flex-1)          | Center zone (flex-1)     | Right zone (flex-1)   |
| chevron + icon btn + name   | ✏️  ➕  ·  🗑️            | tag count badge        |
```

- **Left zone** — `flex-1, min-w-0`: contains the expand chevron, icon button, and category name (truncated). Name gets remaining space.
- **Center zone** — `flex-1, flex justify-center items-center`: contains the action button group, always centered in the card. This guarantees pixel-perfect vertical alignment across all cards regardless of name length.
- **Right zone** — `flex-1, flex justify-end items-center`: contains the tag count badge, pinned to the far right.

### Action buttons

- **Always visible** — no `opacity-0 group-hover:opacity-100` wrapper on desktop.
- **Emoji icons only** — `✏️` (rename), `➕` (add tag), `🗑️` (delete). No text labels, no tinted backgrounds.
- **Divider** — a subtle 1px vertical divider between `➕` and `🗑️` to visually separate safe actions from the destructive one.
- **Protected categories** — emoji buttons for protected categories remain `cursor-not-allowed` and visually dimmed (existing logic unchanged).

### Deduplication of button markup

Currently the file renders two separate button groups — one for desktop hover (`hidden md:flex opacity-0 group-hover:opacity-100`) and one for mobile always-visible (`md:hidden flex`). These are collapsed into a single group that is always visible on both breakpoints. The `group` class and `group-hover` variants on this section are removed.

### What does NOT change

- Tag chip area (expand/collapse, search highlight, inline editing, relocate/delete tag buttons)
- Icon picker button on the category icon
- Modals (create category, add tag, relocate tag, icon picker)
- Mobile layout — already always-visible; the collapsed single group works on mobile too
- Search, expand/collapse all, header, loading skeleton

## Files

| File | Change |
|---|---|
| `frontend/src/pages/Categories.tsx` | Replace category header row markup with 3-zone layout; remove duplicate button blocks |

No new files, no new hooks, no API changes, no i18n key additions (button actions already have `title` attributes with existing keys).
