---
paths:
  - "frontend/src/pages/**/*.{ts,tsx}"
---

# Frontend Pages - Route Views

## Purpose
Pages represent top-level views mapped to Routes in the application. They orchestrate layout, instantiate feature components, and handle page-level data fetching strategies.

## Core Principle: Composition & Layout

### What Pages DO:
- **Define Layout** - Header, Sidebar, Main Content area
- **Compose Components** - Assemble feature components
- **Route Parameters** - Read `useParams`, `useSearchParams`
- **Page Metadata** - Set document title
- **Data Orchestration** - Prefetch queries if needed

### What Pages DO NOT DO:
- **Complex UI rendering** - Delegate to Components
- **Direct API Logic** - Use custom hooks
- **Global State Logic** - Use Stores

## Standard Page Structure

```tsx
import React from 'react';
import { useParams } from 'react-router-dom';
import { TransactionTable } from '../components/TransactionTable';
import { MonthlySummary } from '../components/MonthlySummary';

export const DashboardPage: React.FC = () => {
  const { year, month } = useParams();

  return (
    <div className="flex flex-col gap-6 p-6">
      <header className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
      </header>

      <section className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="md:col-span-2">
           <MonthlySummary year={year} month={month} />
        </div>
      </section>

      <section>
        <h2 className="text-lg font-semibold mb-4">Recent Transactions</h2>
        <TransactionTable limit={5} />
      </section>
    </div>
  );
};
```

## Routing
- Pages are registered in `App.tsx` or a Router config.
- Use `react-router-dom` for navigation logic.
- Lazy load pages for better performance (`React.lazy`).

## Best Practices
1. **Clean Layouts**: Use CSS Grid/Flexbox for page structure.
2. **Route Guards**: Protect private pages (require login).
3. **Error Handling**: Display fallback UI if page-level data fails.
4. **Responsive**: Ensure pages work on mobile/desktop via Tailwind breakpoints (`md:`, `lg:`).
