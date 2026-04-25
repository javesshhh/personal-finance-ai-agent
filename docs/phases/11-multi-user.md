# Phase 11 — Multi-User Support

Add user identity, authentication, and data isolation so multiple people can use the same FinSight deployment with their own private data.

---

## Why this is a separate phase

All earlier phases build features assuming one global user. Adding multi-user touches the database schema, every service query, every API endpoint, and the MCP layer. Doing it last means the feature set is proven before introducing auth complexity.

---

## What changes

### 1. User model & registration

New `users` table:

```
users
  id          UUID (PK)
  email       TEXT UNIQUE NOT NULL
  name        TEXT
  password    TEXT (bcrypt hash)
  created_at  TIMESTAMP
```

New endpoints:
- `POST /api/v1/auth/register` — create account
- `POST /api/v1/auth/login` — returns JWT access token
- `GET /api/v1/auth/me` — current user info

**Library:** `python-jose` for JWT, `passlib[bcrypt]` for password hashing.

---

### 2. Foreign keys on all user-owned tables

Every table gets a `user_id UUID NOT NULL REFERENCES users(id)` column:

| Table | Change |
|-------|--------|
| `transactions` | Add `user_id` |
| `subscriptions` | Add `user_id` |
| `health_scores` | Add `user_id` |
| `budgets` | Add `user_id` |
| `goals` | Add `user_id` |

Generate one Alembic migration covering all tables at once.

---

### 3. Auth dependency

```python
# core/auth.py
async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    ...
```

Every protected router injects `current_user: User = Depends(get_current_user)`.

---

### 4. Filter every query by user_id

Every service function gets a `user_id: UUID` parameter added. All `SELECT`, `INSERT`, and `UPDATE` statements gain a `.where(Model.user_id == user_id)` clause.

Files to update:
- `app/services/transaction_service.py`
- `app/services/subscription_service.py`
- `app/services/scenario_service.py`
- `app/services/health_score_service.py`
- `app/services/budget_service.py`
- `app/services/goal_service.py`

---

### 5. MCP server — user identity

The MCP server currently connects as a nameless caller. With multi-user, it needs to know whose data to query.

**Approach:** Add a `user_email` config field to `claude_desktop_config.json`. On startup, the MCP server looks up (or creates) the user by email and scopes all tool calls to that `user_id`.

```json
"env": {
  "FINSIGHT_USER_EMAIL": "you@example.com",
  ...
}
```

Each person who connects Claude Desktop sets their own email in the config — their MCP tools only see their own data.

---

### 6. Token-based auth for the REST API

All existing endpoints gain auth:

```python
@router.get("/spending")
async def get_spending(
    ...,
    current_user: User = Depends(get_current_user),
):
    return await transaction_service.get_spending_by_category(db, current_user.id, ...)
```

Public routes (no auth needed): `GET /health`, `POST /auth/register`, `POST /auth/login`.

---

## Step-by-step checklist

- [ ] Add `python-jose[cryptography]` and `passlib[bcrypt]` to `requirements.in`, run `pip-compile`
- [ ] Create `app/models/user.py` — User ORM model
- [ ] Create Alembic migration: add `users` table + `user_id` FK to all tables
- [ ] Run `alembic upgrade head`
- [ ] Create `core/auth.py` — JWT encode/decode, `get_current_user` dependency
- [ ] Create `app/services/user_service.py` — register, login, get_by_email
- [ ] Create `app/schemas/user.py` — UserCreate, UserRead, TokenResponse
- [ ] Create `api/auth.py` — register + login + me endpoints
- [ ] Register auth router in `core/app.py`
- [ ] Update all service functions to accept and filter by `user_id`
- [ ] Update all API endpoints to inject `current_user` and pass `user_id` to services
- [ ] Update MCP tools — resolve user from `FINSIGHT_USER_EMAIL` env var at startup
- [ ] Update `claude_desktop_config.json` to include `FINSIGHT_USER_EMAIL`
- [ ] Manual test: register two users, import different CSVs, verify data isolation
- [ ] Update `README.md` with new auth endpoints

---

## Database migration strategy

The tricky part: `user_id` is NOT NULL but existing rows have no user. Two options:

**Option A (clean slate):** Drop all data, add `NOT NULL` column directly.
```bash
# Wipe dev data
alembic downgrade base
alembic upgrade head
```

**Option B (preserve data):** Add column as nullable → backfill with a default user → add NOT NULL constraint.
```sql
ALTER TABLE transactions ADD COLUMN user_id UUID REFERENCES users(id);
-- insert a default user, update all rows
ALTER TABLE transactions ALTER COLUMN user_id SET NOT NULL;
```

For a development/demo project, Option A is simpler. For production with real user data, use Option B.

---

## Security notes

- Passwords must be bcrypt-hashed — never store plaintext
- JWT secret must be in `.env` as `JWT_SECRET` — never hardcoded
- JWT expiry: 7 days for personal use, 15 minutes + refresh token for production
- All endpoints must return 401 (not 403 or 404) for missing/invalid tokens so clients can re-authenticate

---

## New files

```
api/auth.py
app/models/user.py
app/schemas/user.py
app/services/user_service.py
core/auth.py
migrations/versions/XXXX_add_multi_user.py
```
