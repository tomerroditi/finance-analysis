---
paths:
  - "frontend/src/utils/**/*.{ts,tsx}"
---

# Frontend Utils Layer - Helper Functions

## Purpose
Utility modules contain **pure helper functions** and reusable classes for the Frontend. These are stateless, focused, and provide common functionality across components.

## Core Principle: Pure Functions

### What Utils DO:
- **Pure transformations** - Stateless data manipulation
- **Common calculations** - Formatting currency, percentages
- **Date helpers** - Formatting dates for UI (using `date-fns` or native `Intl`)
- **Validation helpers** - Form validation regex

### What Utils DO NOT DO:
- **React Hooks** - Use `hooks/` directory for code that uses `useState`/`useEffect`
- **UI Rendering** - Use components
- **API Calls** - Use services/api

**Golden Rule:** Utils are helpers - stateless, reusable, no side effects.

## Best Practices

1. **Pure functions** - No side effects, predictable output
2. **TypeScript** - Strong typing for arguments and return values
3. **JSDoc** - Document complex functions
4. **Shared logic** - Extract logic used in 2+ components
5. **No DOM access** - Avoid direct DOM manipulation

## Common Categories
- `formatters.ts`: Currency, Date, String formatting
- `validation.ts`: Input validation helpers
- `constants.ts`: Shared constants (if not in a separate config)
