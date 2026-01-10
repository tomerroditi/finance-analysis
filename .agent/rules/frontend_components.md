---
trigger: glob
globs: frontend/src/components/**/*.{ts,tsx}
---

# Frontend Components - UI Implementation

## Purpose
Components contain **ALL UI implementation logic** for the React application. They render HTML/JSX, handle user interactions, manage local state, and display data fetched via hooks.

## Core Principle: Atomic Design & Composition

### What Components DO:
✅ **Render UI (JSX)** - HTML structure, Tailwind styling  
✅ **Handle interactions** - onClick, onChange, onSubmit  
✅ **Manage local state** - useState, useReducer  
✅ **Display data** - Props or data from React Query hooks  
✅ **Simple validation** - Form validation before submission  
✅ **Use Tailwind CSS** - For strict, utility-first styling (version 4)

### What Components DO NOT DO:
❌ **Direct API calls** - No axios directly (use custom hooks/services)  
❌ **Business logic** - Complex calculations belong in backend or hooks  
❌ **Direct Page Routing** - Use useNavigate or Link  
❌ **Global State Management** - Use Context or Zustand stores, not prop drilling

**Golden Rule:** Components focus on "how it looks and feels" - Hooks/Services handle "data fetching and business logic".

## Architecture Patterns

### Component Structure
**Functional Components** with TypeScript

### Styling with Tailwind CSS 4
- Use utility classes directly in className
- Use specific colors/spacing from the design system
- Avoid inline styles unless dynamic values are needed
- Use clsx or tailwind-merge for conditional class joining

### Data Fetching
- Use **TanStack Query (React Query)** for all server state
- Create custom hooks for reusable queries
- Handle isLoading, isError states gracefully

### State Management
- **Local State:** useState for UI toggles, form inputs
- **Form State:** Consider react-hook-form for complex forms
- **Global State:** Zustand for app-wide UI state (modals, sidebar)
- **Server State:** TanStack Query cache

## Best Practices
1. **Typed Props**: Always define interface Props for components
2. **Small & Focused**: Split large components into smaller sub-components
3. **Reusable**: Avoid hardcoding specific business logic if the component is generic
4. **Accessibility**: Use semantic HTML
5. **No st. calls**: This is React, not Streamlit
6. **Error Boundaries**: Wrap critical sections with Error Boundaries

## Common Components
- Button, Input, Card (UI primitives)
- TransactionTable, BudgetChart (Feature components)
- Modal, Dialog (Overlays)
