# Phase 11 — Session-Based Identity & PDF Support

Replace the single-user global data model with named sessions, and add PDF bank statement parsing alongside CSV import.

---

## Why sessions instead of full auth

Full JWT auth (users table, passwords, tokens) is the right call for a product with multiple real users. For a personal finance tool used by one or a few people from Claude Desktop, sessions are simpler and equally effective:

- No passwords to manage
- No token expiry to handle in MCP tools
- Session name is human-readable and self-documenting ("Javesh 2025", "Joint Account")
- Each person sets their session name in their own Claude Desktop config — zero friction

---

## Part A — Session-Based Identity

### 1. Sessions table

```sql
sessions
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid()
  name        TEXT UNIQUE NOT NULL     -- "Javesh 2025", "Joint Account"
  created_at  TIMESTAMP DEFAULT now()
```

### 2. Foreign key on all owned tables

Add `session_id UUID NOT NULL REFERENCES sessions(id)` to:

| Table | Change |
|-------|--------|
| `transactions` | Add `session_id` |
| `subscriptions` | Add `session_id` |
| `health_scores` | Add `session_id` |
| `budgets` | Add `session_id` |
| `goals` | Add `session_id` |

One Alembic migration covers all tables.

**Migration strategy for existing data:** existing rows get assigned to a default session called `"default"` created during the migration. No data is lost.

### 3. Session API endpoints

```
POST   /api/v1/sessions/           — create a session (body: {"name": "Javesh 2025"})
GET    /api/v1/sessions/           — list all sessions (id + name + created_at)
DELETE /api/v1/sessions/{id}       — delete a session and all its data
```

### 4. Session selection on document upload

When importing a file (CSV or PDF), the request must include a `session_id`:

```
POST /api/v1/transactions/import-csv?session_id=<uuid>
POST /api/v1/transactions/import-pdf?session_id=<uuid>
```

**The upload flow from a client perspective:**
1. Call `GET /api/v1/sessions/` → get list of sessions
2. Show list + "New session" option
3. If "New session" → call `POST /api/v1/sessions/` with chosen name → get back `session_id`
4. Upload file with that `session_id`

### 5. Session scoping in all service functions

Every service function gains a `session_id: UUID` parameter. All queries gain `.where(Model.session_id == session_id)`.

Files to update:
- `app/services/transaction_service.py`
- `app/services/subscription_service.py`
- `app/services/scenario_service.py`
- `app/services/health_score_service.py`
- `app/services/budget_service.py`
- `app/services/goal_service.py`

### 6. MCP tools — session identity via env var

The MCP server is launched by Claude Desktop as a subprocess. Each user sets their session name in `claude_desktop_config.json`:

```json
"env": {
  "FINSIGHT_SESSION": "Javesh 2025",
  ...
}
```

On startup, the MCP server resolves the session name to a `session_id` (creating the session if it doesn't exist yet). All tool calls use this `session_id` internally — the user never has to pass it in queries.

### 7. Updated MCP tool signatures

All existing and future tools get session context injected automatically at the server level — callers (Claude Desktop) don't need to pass session name explicitly:

| Tool | Change |
|------|--------|
| `get_spending(start_date, end_date)` | session resolved from env at startup, no change to signature |
| `compare_months(year_a, month_a, year_b, month_b)` | same |
| `audit_subscriptions()` | same |
| `flag_price_changes()` | same |
| `run_scenario(...)` | same |
| `get_health_score()` | same |
| `set_goal(...)` | same |
| `get_goals()` | same |

New tools added in this phase:

| Tool | Description |
|------|-------------|
| `list_sessions()` | Returns all session names — useful when user wants to switch context |
| `import_transactions(file_path)` | Import a local CSV or PDF by file path, into the active session |

---

## Part B — PDF Bank Statement Parsing

### How PDF parsing works

Bank statement PDFs come in two forms:

1. **Tabular PDFs** (most modern bank statements) — rows and columns are structured. `pdfplumber` extracts them reliably.
2. **Text-dump PDFs** (scanned or older formats) — unstructured text. Claude API parses these by reading the raw text and extracting transaction rows.

### Pipeline

```
PDF uploaded
    ↓
pdfplumber extracts text/tables from each page
    ↓
Does it look tabular? (has rows with date + amount patterns)
    ↓ yes                          ↓ no
Parse table rows directly     Send text to Claude API:
into transactions             "Extract transactions as JSON"
    ↓                              ↓
Normalize into TransactionCreate list
    ↓
Run through existing import_csv deduplication + categorization pipeline
    ↓
Return CSVImportResult
```

### New endpoint

```
POST /api/v1/transactions/import-pdf?session_id=<uuid>
Content-Type: multipart/form-data
file: <pdf file>
```

Returns the same `CSVImportResult` schema as CSV import.

### New service function

```python
# app/services/pdf_parser.py
async def parse_pdf(pdf_content: bytes) -> list[TransactionCreate]:
    ...
```

Internally tries tabular extraction first, falls back to Claude API text parsing.

### Library

`pdfplumber` — pure Python, no system dependencies, handles both text and table extraction cleanly. Add to `requirements.in`.

### Claude API prompt for unstructured PDFs

```
Given the following bank statement text, extract all transactions.
Return a JSON array where each item has: date (YYYY-MM-DD), description (string), amount (positive number).
Ignore headers, footers, account summaries, and running balances.
```

If Claude API is unavailable (no credits), fall back to regex-based date+amount detection — catches most tabular formats.

---

## Step-by-step checklist

### Session infrastructure
- [ ] Add `pdfplumber` to `requirements.in`, run `pip-compile`
- [ ] Create `app/models/session.py` — Session ORM model
- [ ] Create Alembic migration: add `sessions` table, add `session_id` FK to all tables, backfill with default session
- [ ] Run `alembic upgrade head`
- [ ] Create `app/schemas/session.py` — SessionCreate, SessionRead
- [ ] Create `app/services/session_service.py` — create, list, delete, get_or_create_by_name
- [ ] Create `api/sessions.py` — session endpoints
- [ ] Register sessions router in `core/app.py`
- [ ] Update all service functions to accept `session_id: UUID`
- [ ] Update all API endpoints to require and pass `session_id`
- [ ] Add `FINSIGHT_SESSION` to `core/config.py` settings
- [ ] Update `mcp_server/server.py` to resolve session on startup
- [ ] Update all MCP tools to use the session-scoped session_id
- [ ] Add `list_sessions` and `import_transactions` MCP tools

### PDF support
- [ ] Create `app/services/pdf_parser.py` — tabular + Claude API fallback extraction
- [ ] Create `api/pdf_import.py` or add `import-pdf` route to `api/transactions.py`
- [ ] Manual test: upload a real bank statement PDF, verify transactions extracted correctly
- [ ] Test deduplication works across mixed CSV + PDF imports for same period

---

## New files

```
app/models/session.py
app/schemas/session.py
app/services/session_service.py
app/services/pdf_parser.py
api/sessions.py
migrations/versions/XXXX_add_sessions.py
```

## Files updated

```
core/config.py                  — FINSIGHT_SESSION setting
core/app.py                     — register sessions router
api/transactions.py             — session_id param on import endpoints
mcp_server/server.py            — resolve session on startup
mcp_server/tools/transactions.py — use session_id
mcp_server/tools/subscriptions.py
mcp_server/tools/scenarios.py
mcp_server/tools/health_score.py
mcp_server/tools/goals.py
app/services/*.py               — all service functions gain session_id param
app/models/transaction.py       — add session_id FK
app/models/subscription.py      — add session_id FK
app/models/health_score.py      — add session_id FK
app/models/budget.py            — add session_id FK
app/models/goal.py              — add session_id FK
```
