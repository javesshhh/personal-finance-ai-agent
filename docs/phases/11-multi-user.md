# Phase 11 — Multi-User Support

Add proper user accounts so multiple people can use the same FinSight deployment, each with their own private sessions and data.

---

## Context

Sessions are already implemented (Phase 03). A session is a named data workspace — "hdfc credit card", "sbi savings", etc. Right now all sessions are globally visible with no ownership — anyone with API access can see everyone's data.

Phase 11 adds a `users` table and ties each session to a user. Each user:
- Registers with email + password
- Gets a JWT token on login
- Can only see and query their own sessions

---

## What changes

### 1. Users table

```sql
users
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid()
  email       TEXT UNIQUE NOT NULL
  name        TEXT
  password    TEXT  -- bcrypt hash, never plaintext
  created_at  TIMESTAMP DEFAULT now()
```

### 2. Add `user_id` FK to sessions

```sql
ALTER TABLE sessions ADD COLUMN user_id UUID NOT NULL REFERENCES users(id);
```

Migration strategy for existing sessions: create a default user, backfill all existing sessions to it (same pattern used when adding `session_id` to transactions in Phase 03).

### 3. Auth endpoints

```
POST /api/v1/auth/register   — {"email": "...", "password": "...", "name": "..."}
POST /api/v1/auth/login      — {"email": "...", "password": "..."} → {"access_token": "..."}
GET  /api/v1/auth/me         — returns current user profile
```

**Library:** `python-jose[cryptography]` for JWT, `passlib[bcrypt]` for password hashing.

### 4. Auth dependency

```python
# core/auth.py
async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    ...
```

### 5. Session endpoints scoped to current user

`GET /api/v1/sessions/` returns only the logged-in user's sessions.
`POST /api/v1/sessions/` creates a session owned by the logged-in user.
`DELETE /api/v1/sessions/{id}` only works on the user's own sessions.

### 6. MCP server — user identity via env var

Each person sets their credentials in `claude_desktop_config.json`:

```json
"env": {
  "FINSIGHT_USER_EMAIL": "javesh@example.com",
  "FINSIGHT_USER_PASSWORD": "...",
  "FINSIGHT_SESSION": "hdfc credit card",
  ...
}
```

On startup the MCP server authenticates, gets a JWT, and uses it for all tool calls. Tools remain signature-unchanged — session resolution already handles the rest.

---

## Step-by-step checklist

- [ ] Add `python-jose[cryptography]` and `passlib[bcrypt]` to `requirements.in`, run `pip-compile`
- [ ] Create `app/models/user.py` — User ORM model
- [ ] Create Alembic migration: add `users` table, add `user_id` FK to `sessions`, backfill with default user
- [ ] Run `alembic upgrade head`
- [ ] Create `core/auth.py` — JWT encode/decode, `get_current_user` dependency
- [ ] Create `app/services/user_service.py` — register, authenticate, get_by_email
- [ ] Create `app/schemas/user.py` — UserCreate, UserRead, TokenResponse
- [ ] Create `api/auth.py` — register + login + me endpoints
- [ ] Register auth router in `core/app.py`
- [ ] Update `session_service` and `api/sessions.py` to filter by `user_id`
- [ ] Add `FINSIGHT_USER_EMAIL` + `FINSIGHT_USER_PASSWORD` to `core/config.py`
- [ ] Update MCP server to authenticate on startup and pass JWT to tool-level DB calls
- [ ] Update `claude_desktop_config.json` with user credentials
- [ ] Manual test: register two users, import different data, verify isolation

---

## New files

```
app/models/user.py
app/schemas/user.py
app/services/user_service.py
core/auth.py
api/auth.py
migrations/versions/XXXX_add_users_and_user_id_to_sessions.py
```

## Files updated

```
core/config.py          — FINSIGHT_USER_EMAIL, FINSIGHT_USER_PASSWORD
core/app.py             — register auth router
api/sessions.py         — filter by user_id from current_user
app/models/session.py   — add user_id FK
mcp_server/server.py    — authenticate on startup
```
