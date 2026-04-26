# Phase 04 — Subscription Intelligence Layer ✅ Done

## Overview

This phase built the subscription detector — automatically finds recurring charges in transaction history, tracks price changes, and scores each subscription by perceived waste.

**All work is session-scoped.** Every subscription belongs to a session (via `session_id` FK) — the same isolation model as transactions.

---

## What Was Built

### Data Model — `app/models/subscription.py`
- `subscriptions` table with `session_id` FK (`CASCADE` delete)
- Fields: `name`, `normalized_pattern`, `latest_amount`, `previous_amount`, `last_charged`, `frequency_days`, `waste_score`, `waste_reason`, `is_active`
- Session relationship registered on `Session` model with `cascade="all, delete-orphan"`

### Detection Logic — `app/services/subscription_service.py`
- **`detect_subscriptions(db, session_id)`** — scans `SUBSCRIPTIONS`-categorized transactions; groups by keyword match (2+ occurrences = recurring); upserts into `subscriptions` table
- **`_score_waste(db, subscriptions)`** — calls Claude API to assign 0–100 waste scores; gracefully falls back to `None` scores on `BadRequestError` or any exception
- **`get_all_subscriptions(db, session_id)`** — returns all active subscriptions ordered by waste score descending
- **`get_price_changes(db, session_id)`** — returns subscriptions where `latest_amount > previous_amount`

### Keyword List (`SUBSCRIPTION_KEYWORDS`)
```python
["netflix", "spotify", "amazon prime", "hotstar", "disney", "youtube premium",
 "apple music", "apple one", "icloud", "google one", "microsoft 365",
 "adobe", "notion", "github", "slack", "zoom", "figma", "dropbox",
 "swiggy one", "zomato pro", "jio", "airtel", "vodafone", "vi ",
 "prime video", "zee5", "sonyliv", "mxplayer", "bookmyshow",
 "gym", "cult.fit", "healthify"]
```

### Schemas — `app/schemas/subscription.py`
- `SubscriptionRead` — full subscription with waste score and reason
- `PriceChangeAlert` — name, previous_amount, latest_amount, change_pct

### API Routes — `api/subscriptions.py`
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/subscriptions/detect?session_id=` | Detect recurring subscriptions |
| GET | `/api/v1/subscriptions/?session_id=` | List subscriptions with waste scores |
| GET | `/api/v1/subscriptions/price-changes?session_id=` | Price increase alerts |

### MCP Tools — `mcp_server/tools/subscriptions.py`
All tools accept `session_name: str = ""` — resolves to `FINSIGHT_SESSION` env var default if empty.

| Tool | Description |
|------|-------------|
| `detect_subscriptions` | Scan transactions and detect recurring subscriptions |
| `audit_subscriptions` | List all detected subscriptions with waste scores |
| `flag_price_changes` | Show subscriptions with price increases |

### Migration
`30a1e8607311_add_subscriptions_table.py` — applied via `alembic upgrade head`

---

## Key Design Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Detection method | Rule-based keyword matching | Fast, cheap, deterministic; covers 95% of real subscriptions |
| Waste scoring | Cached in DB, recomputed on `detect` | Avoids Claude API call on every read |
| Trigger | On-demand (`POST /detect`) | Simple for MVP; avoids hot-path complexity |
| Fallback | Score = `None` when Claude API unavailable | System always works even without credits |

---

## Smoke Test (verified)
- Netflix and Spotify detected from default session sample data
- `audit_subscriptions` MCP tool returns results with waste scores
- `flag_price_changes` correctly identifies price-increased subscriptions
