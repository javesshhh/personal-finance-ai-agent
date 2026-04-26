# Known Limitations

This file tracks known gaps, edge cases, and design trade-offs in the current implementation.
Updated as each phase is built.

---

## Phase 03 — Transactions

| # | Limitation | Impact | Workaround / Future fix |
|---|-----------|--------|------------------------|
| 1 | **CSV format is fixed** — expects `date`, `description`, `amount` columns in that exact form. Bank-specific column names (e.g. "Txn Date", "Dr/Cr") are not handled. | Requires manual column rename before import | Add a column mapping step or per-bank CSV profile |
| 2 | **Date format must be ISO (YYYY-MM-DD)** in CSVs | Non-ISO dates (e.g. "15/01/2025") fail on import | PDF parser handles multiple formats; CSV parser does not |
| 3 | **Single category per transaction** — no split transactions (e.g. a receipt that is part food, part medicine) | Minor categorization inaccuracy | Out of scope for MVP |
| 4 | **`compare_months` is session-scoped only** — no cross-session month comparison | Cannot ask "Did I spend more overall in Feb vs Jan?" | Cross-session compare_months not yet implemented |
| 5 | **`SHOPPING` category is never assigned by the keyword fallback** — the keyword map sends Amazon/Flipkart/Myntra to `ENTERTAINMENT` | Shopping spend appears under entertainment in keyword-fallback mode | Claude API correctly assigns `SHOPPING`; keyword map needs updating |

---

## Phase 04 — Subscriptions

| # | Limitation | Impact | Workaround / Future fix |
|---|-----------|--------|------------------------|
| 1 | **Subscription detection only scans `SUBSCRIPTIONS`-categorized transactions** — telecoms (Airtel, Jio) are categorized as `UTILITIES` so are missed | Airtel/Jio recurring charges not detected as subscriptions | Extend detection to also scan `UTILITIES` for SUBSCRIPTION_KEYWORDS |
| 2 | **Keyword list is hardcoded** — new services (e.g. a niche SaaS) not in the list won't be detected | Emerging or regional subscriptions missed | Add user-configurable keywords, or switch to AI-based detection |
| 3 | **Waste scoring uses pattern name, not actual description** — Claude sees "Netflix" not the full transaction text | Scores are generic (same score for every Netflix subscriber) | Pass amount + frequency for better personalization |
| 4 | **No subscription cancellation tracking** — `is_active` stays `True`; no way to mark a cancelled subscription | Cancelled subs persist in audit list | Add a `DELETE /subscriptions/{id}` endpoint and MCP tool |
| 5 | **Price change detection requires re-running detect** — previous price is only updated on next `detect_subscriptions` call | Price change won't show until detect is called again after a new bill | Acceptable for MVP; auto-detect on import could be added later |

---

## Phase 05 — Scenario Engine

| # | Limitation | Impact | Workaround / Future fix |
|---|-----------|--------|------------------------|
| 1 | **Single category per scenario** — the MCP tool takes one `category` + `reduction_pct` | Cannot model "cut food 30% AND subscriptions 50%" in one query | Multi-category scenarios not yet supported; ask two separate questions |
| 2 | **No income tracking** — `current_monthly_savings` is always `₹0` | Cannot say "you currently save ₹X/month; with changes you'd save ₹Y" | Add `INCOME` category and income detection |
| 3 | **3-month baseline window is fixed** — recent one-time large purchases skew the average | A laptop purchase in the baseline inflates the "shopping" average | Allow configurable baseline window; filter outliers |
| 4 | **Projection assumes linear savings** — no interest, no inflation, no irregular income | Months-to-goal is approximate, not a financial plan | Acceptable accuracy for conversational use; not a financial advisor |

---

## Cross-Session Deduplication (`app/utils/cross_session.py`)

| # | Limitation | Impact | Workaround / Future fix |
|---|-----------|--------|------------------------|
| 1 | **Detection uses word-overlap + keyword, not amount matching** — relies purely on description text | May miss bill payments with vague descriptions like "Card Payment 1234" | Add amount+timing correlation as a second confirmation layer |
| 2 | **Partial credit card payments not handled** — if you pay ₹10,000 against a ₹15,000 bill, the full bill transaction is excluded but ₹5,000 carried forward is untracked | Slight undercount of outstanding spend | Requires EMI/carry-forward tracking, out of scope for MVP |
| 3 | **`compare_months` does not deduplicate** — only `get_spending` and `run_scenario` apply deduplication for cross-session queries | Month-on-month comparison still double-counts if cross-session | Extend `compare_months` to accept `exclude_ids` |
| 4 | **No deduplication for same-session duplicate detection** — if you import the same statement twice into the same session, the unique constraint handles it; but importing into two different sessions doubles the data | Requires discipline in session naming | Document import rules clearly |

---

## General / Architecture

| # | Limitation | Impact | Workaround / Future fix |
|---|-----------|--------|------------------------|
| 1 | **Single user only** — no authentication, all sessions are globally visible | Not safe for multi-user deployment | Phase 11 adds users table + JWT auth + user_id FK on sessions |
| 2 | **Claude API credits required for full experience** — categorization, waste scoring, and scenario narrative all degrade gracefully but lose quality without credits | Keyword fallback works but is less accurate | Keep API funded; add top-up alert |
| 3 | **No mobile / web UI** — Claude Desktop is the only UX | Requires Claude Desktop to be installed and configured | Phase 10+ could add a web dashboard |
| 4 | **MCP server is local only** — runs on stdio, not exposed over network | Cannot access from phone or other machine | Add HTTP transport option in a later phase |
