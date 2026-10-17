# Finance Analysis — Domain Glossary

Terms the code and its docs use with one fixed meaning. `CLAUDE.md` holds the
conventions and rules; this file only names things.

## Transaction views

**Bank view** — what the tracked accounts did: bank and cash rows, with a
credit-card statement counted as the one bank debit that paid it. Card
purchases themselves are not in it. Answers "how much money left the
accounts this month". _Avoid_: cashflow frame, cash basis.

**Spending view** — purchases one by one, on the day they were made: card
purchases included, the bank-side `Credit Cards` bill left out (it would count
the same purchases twice). Answers "what did we spend it on". _Avoid_:
itemized basis, analysis frame.

Both views share one classification and one set of rules:

- every row is **income**, **expense** or **investment**, or is left out;
- `Ignore` rows (internal transfers, card-bill summaries) are left out — they
  are neither income nor spending;
- a refund matched to its purchase is netted against it, whatever months the
  two fell in; whether a purchase still *awaiting* its refund is dropped is
  part of how a view is asked for.
