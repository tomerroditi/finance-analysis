# Hebrew i18n + Settings Popup — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Hebrew language support with full RTL layout, a settings popup in the sidebar, and translate all user-facing strings using react-i18next.

**Architecture:** react-i18next manages translations via JSON files per language. A settings popover (anchored to sidebar gear icon) lets the user switch language and toggle demo mode. Language choice persists in localStorage. When Hebrew is selected, `document.documentElement.dir` flips to `"rtl"` and the entire layout mirrors.

**Tech Stack:** react-i18next, i18next, Tailwind CSS 4 RTL variants

---

### Task 1: Install i18n Dependencies

**Files:**
- Modify: `frontend/package.json`

**Step 1: Install packages**

Run: `cd /Users/tomer/Desktop/finance-analysis/frontend && npm install i18next react-i18next`

**Step 2: Verify installation**

Run: `cd /Users/tomer/Desktop/finance-analysis/frontend && node -e "require('i18next'); require('react-i18next'); console.log('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore: add i18next and react-i18next dependencies"
```

---

### Task 2: Create i18n Configuration and Translation Files

**Files:**
- Create: `frontend/src/i18n.ts`
- Create: `frontend/src/locales/en.json`
- Create: `frontend/src/locales/he.json`

**Step 1: Create the i18n config**

Create `frontend/src/i18n.ts`:

```typescript
import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./locales/en.json";
import he from "./locales/he.json";

const savedLanguage = localStorage.getItem("language") || "en";

i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    he: { translation: he },
  },
  lng: savedLanguage,
  fallbackLng: "en",
  interpolation: {
    escapeValue: false,
  },
});

// Apply direction and lang on init and language change
function applyDirection(lng: string) {
  const dir = lng === "he" ? "rtl" : "ltr";
  document.documentElement.dir = dir;
  document.documentElement.lang = lng;
}

applyDirection(savedLanguage);

i18n.on("languageChanged", (lng: string) => {
  localStorage.setItem("language", lng);
  applyDirection(lng);
});

export default i18n;
```

**Step 2: Create initial English translation file**

Create `frontend/src/locales/en.json` with a starter structure covering the sidebar, settings popup, and common labels. This will be expanded in later tasks as each page is translated:

```json
{
  "common": {
    "save": "Save",
    "cancel": "Cancel",
    "delete": "Delete",
    "edit": "Edit",
    "add": "Add",
    "close": "Close",
    "confirm": "Confirm",
    "search": "Search",
    "loading": "Loading...",
    "noData": "No data available",
    "yes": "Yes",
    "no": "No",
    "back": "Back",
    "next": "Next",
    "all": "All",
    "total": "Total",
    "month": "Month",
    "year": "Year",
    "amount": "Amount",
    "date": "Date",
    "description": "Description",
    "category": "Category",
    "tag": "Tag",
    "account": "Account",
    "status": "Status",
    "actions": "Actions",
    "uncategorized": "Uncategorized"
  },
  "sidebar": {
    "logo": "Finance",
    "dashboard": "Dashboard",
    "transactions": "Transactions",
    "budget": "Budget",
    "categories": "Categories",
    "investments": "Investments",
    "insurance": "Insurance",
    "dataSources": "Data Sources"
  },
  "settings": {
    "title": "Settings",
    "language": "Language",
    "english": "English",
    "hebrew": "עברית",
    "demoMode": "Demo Mode"
  },
  "globalSearch": {
    "placeholder": "Search transactions, categories, or tags...",
    "minChars": "Type at least 2 characters to search...",
    "noResults": "No results found",
    "transaction": "Transaction",
    "category": "Category",
    "tag": "Tag",
    "shortcut": "Search"
  },
  "dashboard": {
    "title": "Dashboard",
    "totalIncome": "Total Income",
    "totalExpenses": "Total Expenses",
    "totalBankBalance": "Total Bank Balance",
    "totalInvestments": "Total Investments",
    "netWorth": "Net Worth",
    "bankBalance": "Bank Balance",
    "investmentValue": "Investment Value",
    "cashBalance": "Cash Balance",
    "incomeVsExpenses": "Income vs Expenses",
    "expensesByCategory": "Expenses by Category",
    "netBalanceOverTime": "Net Balance Over Time",
    "netWorthOverTime": "Net Worth Over Time",
    "cashFlow": "Cash Flow",
    "incomeBySource": "Income by Source",
    "budgetProgress": "Budget Progress",
    "recentTransactions": "Recent Transactions",
    "financialHealth": "Financial Health",
    "monthlyChange": "Monthly Change",
    "viewAll": "View All",
    "income": "Income",
    "expenses": "Expenses",
    "balance": "Balance",
    "refunds": "Refunds",
    "wealthGrowth": "Wealth Growth",
    "wealthDeficit": "Wealth Deficit",
    "unknown": "Unknown",
    "priorWealth": "Prior Wealth",
    "all": "All",
    "portfolioAllocation": "Portfolio Allocation",
    "accountBalances": "Account Balances",
    "cashBalances": "Cash Balances"
  },
  "transactions": {
    "title": "Transactions",
    "table": {
      "date": "Date",
      "description": "Description",
      "amount": "Amount",
      "category": "Category",
      "tag": "Tag",
      "account": "Account",
      "source": "Source",
      "memo": "Memo",
      "chargedAmount": "Charged Amount",
      "originalAmount": "Original Amount"
    },
    "filters": {
      "search": "Search descriptions...",
      "category": "Category",
      "tag": "Tag",
      "source": "Source",
      "dateRange": "Date Range",
      "amountRange": "Amount Range",
      "clearAll": "Clear All Filters"
    },
    "bulk": {
      "selected": "selected",
      "categorize": "Categorize",
      "tag": "Tag",
      "delete": "Delete",
      "split": "Split",
      "createRule": "Create Rule",
      "linkRefund": "Link Refund"
    },
    "pagination": {
      "showing": "Showing",
      "of": "of",
      "perPage": "per page"
    },
    "autoTagging": "Auto Tagging",
    "addCash": "Add Cash Transaction",
    "addInvestment": "Add Investment Transaction"
  },
  "budget": {
    "title": "Budget",
    "monthlyBudget": "Monthly Budget",
    "projectBudgets": "Project Budgets",
    "addBudget": "Add Budget",
    "addProject": "Add Project",
    "spent": "Spent",
    "remaining": "Remaining",
    "overBudget": "Over Budget",
    "onTrack": "On Track",
    "totalBudget": "Total Budget",
    "noBudgets": "No budgets configured",
    "editRule": "Edit Rule",
    "deleteRule": "Delete Rule"
  },
  "categories": {
    "title": "Categories",
    "addCategory": "Add Category",
    "addTag": "Add Tag",
    "editCategory": "Edit Category",
    "editTag": "Edit Tag",
    "deleteCategory": "Delete Category",
    "deleteTag": "Delete Tag",
    "categoryName": "Category Name",
    "tagName": "Tag Name",
    "icon": "Icon",
    "emoji": "Emoji",
    "color": "Color",
    "taggingRules": "Tagging Rules",
    "addRule": "Add Rule",
    "priority": "Priority",
    "pattern": "Pattern",
    "noTags": "No tags in this category"
  },
  "investments": {
    "title": "Investments",
    "addInvestment": "Add Investment",
    "editInvestment": "Edit Investment",
    "closeInvestment": "Close Investment",
    "reopenInvestment": "Reopen Investment",
    "profitLoss": "Profit / Loss",
    "roi": "ROI",
    "totalDeposits": "Total Deposits",
    "totalWithdrawals": "Total Withdrawals",
    "netInvested": "Net Invested",
    "currentBalance": "Current Balance",
    "open": "Open",
    "closed": "Closed",
    "balanceHistory": "Balance History",
    "addSnapshot": "Add Snapshot",
    "addTransaction": "Add Transaction",
    "interestRate": "Interest Rate",
    "fixedRate": "Fixed Rate",
    "variableRate": "Variable Rate",
    "startDate": "Start Date",
    "closeDate": "Close Date",
    "institution": "Institution",
    "accountName": "Account Name"
  },
  "dataSources": {
    "title": "Data Sources",
    "addAccount": "Add Account",
    "editAccount": "Edit Account",
    "deleteAccount": "Delete Account",
    "scrape": "Scrape",
    "scrapeAll": "Scrape All",
    "lastScraped": "Last Scraped",
    "neverScraped": "Never Scraped",
    "provider": "Provider",
    "accountType": "Account Type",
    "banks": "Banks",
    "creditCards": "Credit Cards",
    "insurances": "Insurances",
    "status": "Status",
    "active": "Active",
    "error": "Error",
    "scraping": "Scraping...",
    "credentials": "Credentials",
    "username": "Username",
    "password": "Password"
  },
  "modals": {
    "confirm": {
      "title": "Confirm Action",
      "deleteMessage": "Are you sure you want to delete this? This action cannot be undone.",
      "yes": "Yes, Delete",
      "no": "Cancel"
    },
    "split": {
      "title": "Split Transaction",
      "originalAmount": "Original Amount",
      "remaining": "Remaining",
      "addSplit": "Add Split",
      "splitAmount": "Split Amount"
    },
    "linkRefund": {
      "title": "Link Refund",
      "selectTransaction": "Select a transaction to link as refund"
    },
    "project": {
      "title": "Project Budget",
      "projectName": "Project Name",
      "startDate": "Start Date",
      "endDate": "End Date",
      "budgetAmount": "Budget Amount"
    },
    "budgetRule": {
      "title": "Budget Rule",
      "category": "Category",
      "tag": "Tag",
      "monthlyLimit": "Monthly Limit"
    },
    "transactionForm": {
      "addCash": "Add Cash Transaction",
      "editCash": "Edit Cash Transaction",
      "addInvestment": "Add Investment Transaction",
      "editInvestment": "Edit Investment Transaction",
      "amount": "Amount",
      "date": "Date",
      "description": "Description",
      "category": "Category",
      "tag": "Tag",
      "account": "Account"
    }
  },
  "services": {
    "creditCard": "Credit Card",
    "bank": "Bank",
    "cash": "Cash",
    "investment": "Investment",
    "insurance": "Insurance"
  }
}
```

**Step 3: Create Hebrew translation file**

Create `frontend/src/locales/he.json` with the same structure but Hebrew values. This is a large file — create it with the same keys as `en.json` but translated to Hebrew. Key examples:

```json
{
  "common": {
    "save": "שמור",
    "cancel": "ביטול",
    "delete": "מחק",
    "edit": "ערוך",
    "add": "הוסף",
    "close": "סגור",
    "confirm": "אשר",
    "search": "חיפוש",
    "loading": "טוען...",
    "noData": "אין נתונים זמינים",
    "yes": "כן",
    "no": "לא",
    "back": "חזור",
    "next": "הבא",
    "all": "הכל",
    "total": "סה\"כ",
    "month": "חודש",
    "year": "שנה",
    "amount": "סכום",
    "date": "תאריך",
    "description": "תיאור",
    "category": "קטגוריה",
    "tag": "תגית",
    "account": "חשבון",
    "status": "סטטוס",
    "actions": "פעולות",
    "uncategorized": "ללא קטגוריה"
  },
  "sidebar": {
    "logo": "פיננסים",
    "dashboard": "לוח בקרה",
    "transactions": "תנועות",
    "budget": "תקציב",
    "categories": "קטגוריות",
    "investments": "השקעות",
    "insurance": "ביטוח",
    "dataSources": "מקורות מידע"
  },
  "settings": {
    "title": "הגדרות",
    "language": "שפה",
    "english": "English",
    "hebrew": "עברית",
    "demoMode": "מצב הדגמה"
  },
  "globalSearch": {
    "placeholder": "חיפוש תנועות, קטגוריות או תגיות...",
    "minChars": "הקלד לפחות 2 תווים לחיפוש...",
    "noResults": "לא נמצאו תוצאות",
    "transaction": "תנועה",
    "category": "קטגוריה",
    "tag": "תגית",
    "shortcut": "חיפוש"
  },
  "dashboard": {
    "title": "לוח בקרה",
    "totalIncome": "סה\"כ הכנסות",
    "totalExpenses": "סה\"כ הוצאות",
    "totalBankBalance": "סה\"כ יתרת בנק",
    "totalInvestments": "סה\"כ השקעות",
    "netWorth": "שווי נקי",
    "bankBalance": "יתרת בנק",
    "investmentValue": "ערך השקעות",
    "cashBalance": "יתרת מזומן",
    "incomeVsExpenses": "הכנסות מול הוצאות",
    "expensesByCategory": "הוצאות לפי קטגוריה",
    "netBalanceOverTime": "מאזן נטו לאורך זמן",
    "netWorthOverTime": "שווי נקי לאורך זמן",
    "cashFlow": "תזרים מזומנים",
    "incomeBySource": "הכנסות לפי מקור",
    "budgetProgress": "מעקב תקציב",
    "recentTransactions": "תנועות אחרונות",
    "financialHealth": "בריאות פיננסית",
    "monthlyChange": "שינוי חודשי",
    "viewAll": "הצג הכל",
    "income": "הכנסות",
    "expenses": "הוצאות",
    "balance": "יתרה",
    "refunds": "החזרים",
    "wealthGrowth": "צמיחת הון",
    "wealthDeficit": "גרעון הון",
    "unknown": "לא ידוע",
    "priorWealth": "הון קודם",
    "all": "הכל",
    "portfolioAllocation": "הרכב תיק",
    "accountBalances": "יתרות חשבונות",
    "cashBalances": "יתרות מזומן"
  },
  "transactions": {
    "title": "תנועות",
    "table": {
      "date": "תאריך",
      "description": "תיאור",
      "amount": "סכום",
      "category": "קטגוריה",
      "tag": "תגית",
      "account": "חשבון",
      "source": "מקור",
      "memo": "הערה",
      "chargedAmount": "סכום שחויב",
      "originalAmount": "סכום מקורי"
    },
    "filters": {
      "search": "חיפוש בתיאורים...",
      "category": "קטגוריה",
      "tag": "תגית",
      "source": "מקור",
      "dateRange": "טווח תאריכים",
      "amountRange": "טווח סכומים",
      "clearAll": "נקה את כל המסננים"
    },
    "bulk": {
      "selected": "נבחרו",
      "categorize": "שייך קטגוריה",
      "tag": "תייג",
      "delete": "מחק",
      "split": "פצל",
      "createRule": "צור כלל",
      "linkRefund": "קשר החזר"
    },
    "pagination": {
      "showing": "מציג",
      "of": "מתוך",
      "perPage": "בעמוד"
    },
    "autoTagging": "תיוג אוטומטי",
    "addCash": "הוסף תנועת מזומן",
    "addInvestment": "הוסף תנועת השקעה"
  },
  "budget": {
    "title": "תקציב",
    "monthlyBudget": "תקציב חודשי",
    "projectBudgets": "תקציבי פרויקטים",
    "addBudget": "הוסף תקציב",
    "addProject": "הוסף פרויקט",
    "spent": "הוצא",
    "remaining": "נותר",
    "overBudget": "חריגה מהתקציב",
    "onTrack": "בתקציב",
    "totalBudget": "תקציב כולל",
    "noBudgets": "לא הוגדרו תקציבים",
    "editRule": "ערוך כלל",
    "deleteRule": "מחק כלל"
  },
  "categories": {
    "title": "קטגוריות",
    "addCategory": "הוסף קטגוריה",
    "addTag": "הוסף תגית",
    "editCategory": "ערוך קטגוריה",
    "editTag": "ערוך תגית",
    "deleteCategory": "מחק קטגוריה",
    "deleteTag": "מחק תגית",
    "categoryName": "שם קטגוריה",
    "tagName": "שם תגית",
    "icon": "אייקון",
    "emoji": "אמוג'י",
    "color": "צבע",
    "taggingRules": "כללי תיוג",
    "addRule": "הוסף כלל",
    "priority": "עדיפות",
    "pattern": "תבנית",
    "noTags": "אין תגיות בקטגוריה זו"
  },
  "investments": {
    "title": "השקעות",
    "addInvestment": "הוסף השקעה",
    "editInvestment": "ערוך השקעה",
    "closeInvestment": "סגור השקעה",
    "reopenInvestment": "פתח מחדש",
    "profitLoss": "רווח / הפסד",
    "roi": "תשואה",
    "totalDeposits": "סה\"כ הפקדות",
    "totalWithdrawals": "סה\"כ משיכות",
    "netInvested": "השקעה נטו",
    "currentBalance": "יתרה נוכחית",
    "open": "פתוח",
    "closed": "סגור",
    "balanceHistory": "היסטוריית יתרה",
    "addSnapshot": "הוסף תמונת מצב",
    "addTransaction": "הוסף תנועה",
    "interestRate": "ריבית",
    "fixedRate": "ריבית קבועה",
    "variableRate": "ריבית משתנה",
    "startDate": "תאריך התחלה",
    "closeDate": "תאריך סגירה",
    "institution": "מוסד",
    "accountName": "שם חשבון"
  },
  "dataSources": {
    "title": "מקורות מידע",
    "addAccount": "הוסף חשבון",
    "editAccount": "ערוך חשבון",
    "deleteAccount": "מחק חשבון",
    "scrape": "שליפת נתונים",
    "scrapeAll": "שלוף הכל",
    "lastScraped": "שליפה אחרונה",
    "neverScraped": "לא נשלף אף פעם",
    "provider": "ספק",
    "accountType": "סוג חשבון",
    "banks": "בנקים",
    "creditCards": "כרטיסי אשראי",
    "insurances": "ביטוחים",
    "status": "סטטוס",
    "active": "פעיל",
    "error": "שגיאה",
    "scraping": "שולף נתונים...",
    "credentials": "פרטי התחברות",
    "username": "שם משתמש",
    "password": "סיסמה"
  },
  "modals": {
    "confirm": {
      "title": "אישור פעולה",
      "deleteMessage": "האם אתה בטוח שברצונך למחוק? פעולה זו לא ניתנת לביטול.",
      "yes": "כן, מחק",
      "no": "ביטול"
    },
    "split": {
      "title": "פיצול תנועה",
      "originalAmount": "סכום מקורי",
      "remaining": "נותר",
      "addSplit": "הוסף פיצול",
      "splitAmount": "סכום הפיצול"
    },
    "linkRefund": {
      "title": "קישור החזר",
      "selectTransaction": "בחר תנועה לקישור כהחזר"
    },
    "project": {
      "title": "תקציב פרויקט",
      "projectName": "שם פרויקט",
      "startDate": "תאריך התחלה",
      "endDate": "תאריך סיום",
      "budgetAmount": "סכום תקציב"
    },
    "budgetRule": {
      "title": "כלל תקציב",
      "category": "קטגוריה",
      "tag": "תגית",
      "monthlyLimit": "מגבלה חודשית"
    },
    "transactionForm": {
      "addCash": "הוסף תנועת מזומן",
      "editCash": "ערוך תנועת מזומן",
      "addInvestment": "הוסף תנועת השקעה",
      "editInvestment": "ערוך תנועת השקעה",
      "amount": "סכום",
      "date": "תאריך",
      "description": "תיאור",
      "category": "קטגוריה",
      "tag": "תגית",
      "account": "חשבון"
    }
  },
  "services": {
    "creditCard": "כרטיס אשראי",
    "bank": "בנק",
    "cash": "מזומן",
    "investment": "השקעה",
    "insurance": "ביטוח"
  }
}
```

**Step 4: Import i18n in app entry point**

Modify `frontend/src/main.tsx` — add `import "./i18n";` before the React render call (must be one of the first imports).

**Step 5: Verify the app still loads**

Run: `cd /Users/tomer/Desktop/finance-analysis/frontend && npm run build`
Expected: Build succeeds with no errors

**Step 6: Commit**

```bash
git add frontend/src/i18n.ts frontend/src/locales/en.json frontend/src/locales/he.json frontend/src/main.tsx
git commit -m "feat: add i18n configuration with English and Hebrew translation files"
```

---

### Task 3: Create Settings Popup Component

**Files:**
- Create: `frontend/src/components/layout/SettingsPopup.tsx`
- Modify: `frontend/src/components/layout/Sidebar.tsx`
- Modify: `frontend/src/components/layout/index.ts`

**Step 1: Create the SettingsPopup component**

Create `frontend/src/components/layout/SettingsPopup.tsx`:

```tsx
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { X, Presentation } from "lucide-react";
import { useDemoMode } from "../../context/DemoModeContext";

interface SettingsPopupProps {
  isOpen: boolean;
  onClose: () => void;
  anchorRef: React.RefObject<HTMLButtonElement | null>;
  sidebarOpen: boolean;
}

export function SettingsPopup({ isOpen, onClose, anchorRef, sidebarOpen }: SettingsPopupProps) {
  const { t, i18n } = useTranslation();
  const popupRef = useRef<HTMLDivElement>(null);
  const { isDemoMode, toggleDemoMode } = useDemoMode();
  const isRtl = i18n.language === "he";

  // Close on outside click
  useEffect(() => {
    if (!isOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (
        popupRef.current &&
        !popupRef.current.contains(e.target as Node) &&
        anchorRef.current &&
        !anchorRef.current.contains(e.target as Node)
      ) {
        onClose();
      }
    };
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [isOpen, onClose, anchorRef]);

  if (!isOpen) return null;

  // Position: above the gear icon, anchored to sidebar edge
  const anchorRect = anchorRef.current?.getBoundingClientRect();
  const bottom = anchorRect ? window.innerHeight - anchorRect.top + 8 : 60;
  const positionStyle: React.CSSProperties = isRtl
    ? { bottom, right: sidebarOpen ? 260 : 76, position: "fixed" }
    : { bottom, left: sidebarOpen ? 260 : 76, position: "fixed" };

  const changeLanguage = (lng: string) => {
    i18n.changeLanguage(lng);
  };

  return (
    <div
      ref={popupRef}
      style={positionStyle}
      className="z-[100] w-72 rounded-xl bg-[var(--surface)] border border-[var(--surface-light)] shadow-2xl shadow-black/50 p-4"
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-[var(--text)]">{t("settings.title")}</h3>
        <button
          onClick={onClose}
          className="p-1 rounded-lg hover:bg-[var(--surface-light)] transition-colors"
        >
          <X size={16} className="text-[var(--text-muted)]" />
        </button>
      </div>

      {/* Language */}
      <div className="mb-4">
        <label className="text-xs font-medium text-[var(--text-muted)] mb-2 block">
          {t("settings.language")}
        </label>
        <div className="flex rounded-lg bg-[var(--background)] p-1 gap-1">
          <button
            onClick={() => changeLanguage("en")}
            className={`flex-1 py-1.5 text-sm rounded-md transition-colors ${
              i18n.language === "en"
                ? "bg-[var(--primary)] text-white"
                : "text-[var(--text-muted)] hover:text-white"
            }`}
          >
            {t("settings.english")}
          </button>
          <button
            onClick={() => changeLanguage("he")}
            className={`flex-1 py-1.5 text-sm rounded-md transition-colors ${
              i18n.language === "he"
                ? "bg-[var(--primary)] text-white"
                : "text-[var(--text-muted)] hover:text-white"
            }`}
          >
            {t("settings.hebrew")}
          </button>
        </div>
      </div>

      {/* Demo Mode */}
      <div>
        <label className="text-xs font-medium text-[var(--text-muted)] mb-2 block">
          {t("settings.demoMode")}
        </label>
        <div
          className={`flex items-center gap-3 px-3 py-2 rounded-lg transition-all cursor-pointer ${
            isDemoMode
              ? "bg-amber-500/10 hover:bg-amber-500/20"
              : "bg-[var(--background)] hover:bg-[var(--surface-light)]"
          }`}
          onClick={() => toggleDemoMode(!isDemoMode)}
        >
          <Presentation
            size={18}
            className={`transition-colors shrink-0 ${isDemoMode ? "text-amber-500" : "text-[var(--text-muted)]"}`}
          />
          <span
            className={`text-sm font-medium ${isDemoMode ? "text-amber-500" : "text-[var(--text-muted)]"}`}
          >
            {t("settings.demoMode")}
          </span>
          <div
            className={`ms-auto w-8 h-4 rounded-full relative transition-colors ${isDemoMode ? "bg-amber-500" : "bg-[var(--surface-light)]"}`}
          >
            <div
              className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-all shadow-sm ${
                isDemoMode ? "inset-inline-end-0.5" : "inset-inline-start-0.5"
              }`}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
```

Note the RTL-aware CSS: `ms-auto` (margin-start), `inset-inline-start`, `inset-inline-end` instead of `ml-auto`, `left`, `right`.

**Step 2: Update Sidebar to use SettingsPopup**

Modify `frontend/src/components/layout/Sidebar.tsx`:

1. Add imports: `Settings` from lucide-react, `useRef, useState` from react, `useTranslation` from react-i18next, `SettingsPopup`
2. Replace the hardcoded `navItems` labels with translation keys
3. Replace the Demo Mode toggle block at the bottom with a settings gear icon
4. Add the SettingsPopup component

The sidebar bottom section should become:

```tsx
{/* Settings Icon */}
<div className="absolute bottom-0 inset-inline-start-0 inset-inline-end-0 p-4 border-t border-[var(--surface-light)]">
  <button
    ref={settingsRef}
    onClick={() => setSettingsOpen(!settingsOpen)}
    className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-all w-full ${
      settingsOpen
        ? "bg-[var(--primary)]/10 text-[var(--primary)]"
        : "text-[var(--text-muted)] hover:bg-[var(--surface-light)] hover:text-white"
    }`}
  >
    <SettingsIcon size={20} />
    {sidebarOpen && <span className="text-sm font-medium">{t("settings.title")}</span>}
  </button>
</div>
<SettingsPopup
  isOpen={settingsOpen}
  onClose={() => setSettingsOpen(false)}
  anchorRef={settingsRef}
  sidebarOpen={sidebarOpen}
/>
```

Key changes to the full Sidebar component:
- Nav item labels: change from `item.label` to `t(\`sidebar.${item.key}\`)` where `key` maps to the translation key
- Replace `navItems` array to include a translation key instead of hardcoded label
- Remove the demo mode toggle section entirely (moved to SettingsPopup)
- Remove the `useDemoMode` import and usage (SettingsPopup handles it now)
- Remove `demoLoading` check (SettingsPopup handles it)

**Step 3: Verify the app builds**

Run: `cd /Users/tomer/Desktop/finance-analysis/frontend && npm run build`
Expected: Build succeeds

**Step 4: Commit**

```bash
git add frontend/src/components/layout/SettingsPopup.tsx frontend/src/components/layout/Sidebar.tsx frontend/src/components/layout/index.ts
git commit -m "feat: add settings popup with language toggle and relocated demo mode"
```

---

### Task 4: Add RTL Support to Layout

**Files:**
- Modify: `frontend/src/components/layout/Layout.tsx`
- Modify: `frontend/src/components/layout/Sidebar.tsx`
- Modify: `frontend/src/index.css`

**Step 1: Update Layout.tsx for RTL margin**

The main content uses `ml-64` / `ml-20` for sidebar offset. In RTL, this needs to flip. Use logical properties:

```tsx
// Replace ml-64/ml-20 with ms-64/ms-20 (margin-inline-start)
<main
  className={`transition-all duration-300 ${
    sidebarOpen ? "ms-64" : "ms-20"
  }`}
>
```

`ms-*` is Tailwind's margin-inline-start utility — it applies `margin-left` in LTR and `margin-right` in RTL.

**Step 2: Update Sidebar.tsx for RTL positioning**

Replace directional classes with logical equivalents:
- `fixed left-0` → `fixed inset-inline-start-0`
- `border-r` → `border-e` (border-inline-end)
- Badge: `-right-1` → `-inset-inline-end-1` (or use `end-` utility)

**Step 3: Update the sidebar collapse chevron**

The chevron icons should be aware of RTL. In LTR: collapsed shows `ChevronRight`, expanded shows `ChevronLeft`. In RTL: these should be reversed. Use `i18n.dir()` or check `i18n.language` to conditionally swap.

**Step 4: Add RTL font support in index.css**

Add a Hebrew-friendly font to the font-family stack:

```css
body {
  font-family:
    "Inter",
    "Heebo",
    system-ui,
    -apple-system,
    sans-serif;
}
```

Optionally add a Google Fonts import for Heebo in `index.html`, or rely on system-ui for Hebrew (which works well on macOS/iOS).

**Step 5: Verify RTL works**

Run: `cd /Users/tomer/Desktop/finance-analysis/frontend && npm run build`
Expected: Build succeeds

**Step 6: Commit**

```bash
git add frontend/src/components/layout/Layout.tsx frontend/src/components/layout/Sidebar.tsx frontend/src/index.css
git commit -m "feat: add RTL layout support for Hebrew with logical CSS properties"
```

---

### Task 5: Translate Sidebar and GlobalSearch

**Files:**
- Modify: `frontend/src/components/layout/Sidebar.tsx`
- Modify: `frontend/src/components/layout/GlobalSearch.tsx`

**Step 1: Translate Sidebar nav items**

Update `navItems` to use translation keys:

```tsx
const navItems = [
  { path: "/", icon: LayoutDashboard, key: "dashboard" },
  { path: "/transactions", icon: Receipt, key: "transactions" },
  { path: "/budget", icon: Wallet, key: "budget" },
  { path: "/categories", icon: Tags, key: "categories" },
  { path: "/investments", icon: TrendingUp, key: "investments" },
  { path: "/insurances", icon: Shield, key: "insurance" },
  { path: "/data-sources", icon: Database, key: "dataSources" },
];

// In render:
{sidebarOpen && <span>{t(`sidebar.${item.key}`)}</span>}
```

**Step 2: Translate GlobalSearch**

Replace all hardcoded strings in `GlobalSearch.tsx` with `t()` calls:
- Placeholder: `t("globalSearch.placeholder")`
- Min chars message: `t("globalSearch.minChars")`
- No results: `t("globalSearch.noResults")`
- Type labels (Transaction, Category, Tag): `t("globalSearch.transaction")`, etc.

**Step 3: Verify build**

Run: `cd /Users/tomer/Desktop/finance-analysis/frontend && npm run build`

**Step 4: Commit**

```bash
git add frontend/src/components/layout/Sidebar.tsx frontend/src/components/layout/GlobalSearch.tsx
git commit -m "feat: translate sidebar navigation and global search to support Hebrew"
```

---

### Task 6: Translate Dashboard Page

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

**Step 1: Add useTranslation hook**

```tsx
import { useTranslation } from "react-i18next";
// In component:
const { t } = useTranslation();
```

**Step 2: Replace all hardcoded strings**

This is the largest page (66KB). Key areas to translate:
- KPI card labels: "Total Income" → `t("dashboard.totalIncome")`, etc.
- Chart titles and axis labels
- Section headers: "Financial Health", "Budget Progress", etc.
- Button labels: "View All"
- Legend labels in Plotly charts (pass translated strings to chart data/layout)
- Net worth view toggle labels: "All", "Bank Balance", "Investments", "Net Worth"
- Sankey node labels if they're hardcoded

**Important:** Plotly chart labels (trace names, axis titles) are set in the data/layout objects — translate them where they're defined. Don't try to translate data-driven labels (category names from the backend).

**Step 3: Verify build**

Run: `cd /Users/tomer/Desktop/finance-analysis/frontend && npm run build`

**Step 4: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat: translate Dashboard page strings to support Hebrew"
```

---

### Task 7: Translate Transactions Page and TransactionsTable

**Files:**
- Modify: `frontend/src/pages/Transactions.tsx`
- Modify: `frontend/src/components/TransactionsTable.tsx`
- Modify: `frontend/src/components/transactions/FilterPanel.tsx` (if exists)
- Modify: `frontend/src/components/transactions/AutoTaggingPanel.tsx` (if exists)

**Step 1: Add useTranslation and replace strings in TransactionsTable**

Column headers, pagination text, search placeholder, bulk action labels, empty state messages.

**Step 2: Translate Transactions page**

Page title, action buttons (Add Cash Transaction, Add Investment Transaction), auto-tagging panel toggle.

**Step 3: Translate filter panel and auto-tagging panel**

Filter labels, dropdown placeholders, clear button text.

**Step 4: Verify build**

Run: `cd /Users/tomer/Desktop/finance-analysis/frontend && npm run build`

**Step 5: Commit**

```bash
git add frontend/src/pages/Transactions.tsx frontend/src/components/TransactionsTable.tsx frontend/src/components/transactions/
git commit -m "feat: translate Transactions page and table components"
```

---

### Task 8: Translate Budget Page

**Files:**
- Modify: `frontend/src/pages/Budget.tsx`
- Modify: `frontend/src/components/budget/MonthlyBudgetView.tsx` (if exists)
- Modify: `frontend/src/components/budget/ProjectBudgetView.tsx` (if exists)
- Modify: `frontend/src/components/budget/TransactionCollapsibleList.tsx`
- Modify: `frontend/src/components/BudgetProgressBar.tsx`

**Step 1: Translate all budget-related components**

Tab labels, budget card labels ("Spent", "Remaining", "Over Budget"), add/edit buttons, empty states.

**Step 2: Verify build**

Run: `cd /Users/tomer/Desktop/finance-analysis/frontend && npm run build`

**Step 3: Commit**

```bash
git add frontend/src/pages/Budget.tsx frontend/src/components/budget/ frontend/src/components/BudgetProgressBar.tsx
git commit -m "feat: translate Budget page and components"
```

---

### Task 9: Translate Categories Page

**Files:**
- Modify: `frontend/src/pages/Categories.tsx`

**Step 1: Translate Categories page**

Form labels, button text, emoji picker placeholder, tagging rules section, confirmation dialogs.

**Step 2: Verify build**

Run: `cd /Users/tomer/Desktop/finance-analysis/frontend && npm run build`

**Step 3: Commit**

```bash
git add frontend/src/pages/Categories.tsx
git commit -m "feat: translate Categories page"
```

---

### Task 10: Translate Investments Page

**Files:**
- Modify: `frontend/src/pages/Investments.tsx`

**Step 1: Translate Investments page**

Card labels (Profit/Loss, ROI, Total Deposits, etc.), status badges (Open/Closed), form fields, balance history section, snapshot labels.

**Step 2: Verify build**

Run: `cd /Users/tomer/Desktop/finance-analysis/frontend && npm run build`

**Step 3: Commit**

```bash
git add frontend/src/pages/Investments.tsx
git commit -m "feat: translate Investments page"
```

---

### Task 11: Translate DataSources Page and Remaining Pages

**Files:**
- Modify: `frontend/src/pages/DataSources.tsx`
- Modify: `frontend/src/pages/InsurancesPrototype.tsx`

**Step 1: Translate DataSources page**

Account form labels, provider/service names, scrape status indicators, credential fields.

**Step 2: Translate InsurancesPrototype page**

Any hardcoded strings in the prototype page.

**Step 3: Verify build**

Run: `cd /Users/tomer/Desktop/finance-analysis/frontend && npm run build`

**Step 4: Commit**

```bash
git add frontend/src/pages/DataSources.tsx frontend/src/pages/InsurancesPrototype.tsx
git commit -m "feat: translate Data Sources and Insurance pages"
```

---

### Task 12: Translate Modal Components

**Files:**
- Modify: `frontend/src/components/modals/ConfirmationModal.tsx`
- Modify: `frontend/src/components/modals/TransactionFormModal.tsx`
- Modify: `frontend/src/components/modals/TransactionEditorModal.tsx`
- Modify: `frontend/src/components/modals/SplitTransactionModal.tsx`
- Modify: `frontend/src/components/modals/LinkRefundModal.tsx`
- Modify: `frontend/src/components/modals/ProjectModal.tsx`
- Modify: `frontend/src/components/modals/BudgetRuleModal.tsx`
- Modify: `frontend/src/components/modals/RuleManager.tsx`

**Step 1: Add useTranslation to each modal and replace hardcoded strings**

Title text, button labels, form field labels, confirmation messages.

**Step 2: Verify build**

Run: `cd /Users/tomer/Desktop/finance-analysis/frontend && npm run build`

**Step 3: Commit**

```bash
git add frontend/src/components/modals/
git commit -m "feat: translate all modal components"
```

---

### Task 13: Translate Utility Functions and Common Components

**Files:**
- Modify: `frontend/src/utils/textFormatting.ts`
- Modify: `frontend/src/components/common/SelectDropdown.tsx`
- Modify: `frontend/src/components/DateRangePicker.tsx`

**Step 1: Translate textFormatting.ts**

The `SERVICE_LABELS` and `humanizeAccountType` functions have hardcoded English strings. Use `i18n.t()` (not the hook, since these are utility functions — import `i18n` directly from `../i18n`):

```typescript
import i18n from "../i18n";

export function humanizeService(service: string): string {
  const key = SERVICE_KEY_MAP[service]; // map service names to translation keys
  return key ? i18n.t(`services.${key}`) : toTitleCase(service.replace(/_/g, " "));
}
```

**Step 2: Translate common components**

Placeholder text, labels in SelectDropdown and DateRangePicker.

**Step 3: Verify build**

Run: `cd /Users/tomer/Desktop/finance-analysis/frontend && npm run build`

**Step 4: Commit**

```bash
git add frontend/src/utils/textFormatting.ts frontend/src/components/common/ frontend/src/components/DateRangePicker.tsx
git commit -m "feat: translate utility functions and common components"
```

---

### Task 14: RTL Polish and Visual QA

**Files:**
- Possibly modify: various components for RTL edge cases

**Step 1: Review and fix directional CSS across all components**

Search the entire frontend for LTR-specific classes that need logical equivalents:
- `ml-*` → `ms-*`, `mr-*` → `me-*`
- `pl-*` → `ps-*`, `pr-*` → `pe-*`
- `left-*` → `start-*`, `right-*` → `end-*`
- `text-left` → `text-start`, `text-right` → `text-end`
- `rounded-l-*` → `rounded-s-*`, `rounded-r-*` → `rounded-e-*`
- `border-l-*` → `border-s-*`, `border-r-*` → `border-e-*`

**Important:** Not ALL directional classes need changing — only those that should flip with direction. For example, chart containers may intentionally stay LTR.

**Step 2: Test in browser**

Run: `cd /Users/tomer/Desktop/finance-analysis && python .claude/scripts/with_server.py -- echo "servers started"`
Then manually verify:
- Toggle to Hebrew in settings → layout flips RTL
- Toggle back to English → layout returns to LTR
- Settings popup positions correctly in both modes
- Sidebar collapses/expands correctly in RTL
- Tables render correctly in RTL
- Modals are centered properly in RTL

**Step 3: Fix any visual issues found**

Address edge cases discovered during visual QA.

**Step 4: Commit**

```bash
git add -u frontend/src/
git commit -m "fix: RTL layout polish and visual fixes"
```

---

### Task 15: Fill in Missing Translations

**Files:**
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/he.json`

**Step 1: Audit for missing translation keys**

Search the codebase for any remaining hardcoded strings that should be translated but were missed. Also check for `t()` calls that reference keys not yet in the JSON files.

Run: `cd /Users/tomer/Desktop/finance-analysis/frontend && npx tsc --noEmit`
Expected: No TypeScript errors

**Step 2: Add any missing keys to both JSON files**

**Step 3: Final build verification**

Run: `cd /Users/tomer/Desktop/finance-analysis/frontend && npm run build`
Expected: Clean build

**Step 4: Commit**

```bash
git add frontend/src/locales/
git commit -m "feat: complete translation coverage for all UI strings"
```

---

## Execution Notes

- **Tasks 1-4** are foundational (i18n setup, settings UI, RTL layout) — must be done sequentially
- **Tasks 5-13** are page-by-page translation — can be parallelized across subagents (each page is independent)
- **Tasks 14-15** are cleanup passes — must come after all translations are in place
- When translating, always check both `en.json` and `he.json` — if you add a key, add it in both files
- For Plotly charts: only translate static labels (axis titles, legend names), not data-driven labels
- `ms-*`, `me-*`, `ps-*`, `pe-*` are Tailwind's logical property utilities — they auto-flip in RTL
