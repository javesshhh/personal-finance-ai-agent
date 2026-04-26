# Phase 05 — What-If Scenario Engine ✅ Done

## Overview

The scenario engine answers questions like:
- *"If I cut food delivery by 50%, when can I afford a MacBook Pro?"*
- *"If I save ₹5000 extra/month, when do I hit my emergency fund goal?"*

**Hybrid approach:** Python computes the spending baseline and savings delta deterministically from real transaction data; Claude writes the projection narrative and confirms the months-to-goal. Falls back to deterministic calculation when Claude API is unavailable.

---

## What Was Built

### Schemas — `app/schemas/scenario.py`
```python
class SpendingChange(BaseModel):
    category: TransactionCategory
    reduction_pct: float  # 0-100; validated

class ScenarioRequest(BaseModel):
    spending_changes: list[SpendingChange]
    target_amount: Decimal
    target_description: str       # e.g. "MacBook Pro"
    extra_monthly_savings: Decimal = Decimal("0")

class ScenarioResult(BaseModel):
    months_to_goal: int | None
    projected_monthly_savings: Decimal
    current_monthly_savings: Decimal
    narrative: str
    breakdown: dict[str, str]     # category → "₹X/month → ₹Y/month"
```

### Service — `app/services/scenario_service.py`
- **`run_scenario(db, session_id, request)`** — queries last 3 months of spending via `get_spending_by_category`, computes monthly averages, applies spending cuts, calls `_project_with_claude`
- **`_project_with_claude(...)`** — sends structured JSON to Claude; returns `(months_to_goal, narrative)`; falls back to `_deterministic_projection` on any failure
- **`_deterministic_projection(target_amount, projected_monthly_savings)`** — pure math fallback; always available without API credits

### API Route — `api/scenarios.py`
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/scenarios/run?session_id=` | Run a what-if scenario |

### MCP Tool — `mcp_server/tools/scenarios.py`
**`run_scenario`** — accepts natural language inputs from Claude Desktop:

```
run_scenario(
    category="food",
    reduction_pct=50,
    target_description="MacBook Pro",
    target_amount=90000,
    extra_monthly_savings=0,
    session_name=""           # optional; defaults to FINSIGHT_SESSION
)
```

Output format:
```
Goal [hdfc credit card]: MacBook Pro (₹90,000)
Spending changes:
  food: ₹18,000/month → ₹9,000/month
Projected monthly savings: ₹9,000
Months to goal: 10

By cutting food spending in half you would free up ₹9,000 per month.
At that pace you would reach your MacBook Pro goal in roughly 10 months.
```

---

## Key Design Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Who does the math | Python computes baseline + delta; Claude writes narrative | Numbers are deterministic and testable; Claude adds value through explanation |
| Store results vs on-demand | On-demand | Scenarios are exploratory; rarely repeated identically; no stale-data risk |
| Fallback | `_deterministic_projection` when Claude API fails | System always answers even without API credits |
| Baseline window | Last 3 months | Balances recency vs. statistical noise |
| Input structure | Structured (category enum + float) | Reliable parsing; Claude Desktop handles the NL-to-structured conversion |

---

## Cross-Session Deduplication

When `session_name=""` (all accounts), the engine automatically excludes inter-session transfer transactions to prevent double-counting.

**Example:** If "sbi savings" has `"HDFC Credit Card Bill ₹15,000"` and "hdfc credit card" has individual transactions totalling ₹15,000, only the card transactions are counted — not both.

**Detection logic** (`app/utils/cross_session.py`):
- Two signals must both fire: (1) the description word-overlaps with another session's name, AND (2) contains a payment/bill/transfer keyword
- ATM withdrawals, purchases, and income entries are never flagged even if they share the bank name
- `get_spending_by_category` accepts `exclude_ids: frozenset[int]` to apply the exclusion at the SQL level

**Same deduplication applies to:** `get_spending` MCP tool (cross-session), scenario baseline.

---

## Registration
- `core/app.py` — `scenarios_router` registered at `/api/v1`
- `mcp_server/server.py` — `register_scenario_tools(mcp)` called at startup
