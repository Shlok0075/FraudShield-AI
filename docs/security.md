# Security Guide (Week 14)

Implemented and ready to explain in the viva:

| Control | Implementation |
|---|---|
| Password hashing | bcrypt via passlib (`app/auth/security.py`) — never plaintext |
| JWT authentication | short-lived (60 min) access tokens, secret from `JWT_SECRET` env var, HS256 |
| Role-based access control | `require_role([...])` dependency, per-route (`app/auth/dependencies.py`) |
| Public registration | Always creates `role="user"`; client-supplied `role` field is ignored (`app/routes/auth.py`, `app/schemas/auth.py`) |
| Admin user creation | Protected `POST /api/v1/users` endpoint, requires `require_role(["admin"])` (`app/routes/users.py`) |
| Input validation | Pydantic schemas on every request body (`app/schemas/*.py`) |
| SQL injection prevention | SQLAlchemy ORM, parameterized queries — no raw string-formatted SQL anywhere |
| CORS | explicit allow-list (`CORS_ORIGINS` env var), never `"*"` |
| Rate limiting | slowapi on `/auth/login` (10/min) and `/transactions/predict` (60/min) |
| Secure environment variables | `.env` gitignored, `.env.example` has placeholders only, `pydantic-settings` reads env |
| API authentication | Bearer token required on all non-public routes |
| HTTPS in deployment | enforced by hosting platform (Render/Vercel) |
| Logging | structured request logs (method/path/status/latency) + key events, no passwords/full JWTs logged |
| Audit trails | `audit_logs` table for every admin action |
| Error handling | consistent `{"error": {"code", "message", "details"}}` format, no stack traces leaked |
| Sensitive information protection | never stores real card numbers, CVV, OTP, or real banking credentials — synthetic data only |

## Verified via automated tests (`backend/tests/test_rbac_and_security.py`)
- Unauthorized request → 401
- Invalid JWT → 401
- Wrong-role request → 403 (both admin-only and admin/analyst-only routes)
- SQL-injection-style string in the `amount` field → 422 (rejected by Pydantic validation before reaching SQL)
- Negative amount → 422
- Every error response follows the consistent format

## Rate limiting details
`slowapi.Limiter` with `get_remote_address` as the key function. Exceeding the limit returns HTTP 429. Login is
capped tighter (10/minute) than prediction (60/minute) since brute-force credential guessing is the primary
threat on `/auth/login`, while the simulator legitimately needs a higher prediction throughput.

## Public registration role protection

**Vulnerability fixed:** The public registration endpoint (`POST /api/v1/auth/register`) previously accepted a
`role` field from the client, allowing anyone to register with `role=admin` or `role=analyst` and escalate
privileges.

**Fix:**
- `UserRegister` schema (`app/schemas/auth.py`) no longer accepts a `role` field from the client.
- The registration route (`app/routes/auth.py`) always sets `role="user"` server-side, ignoring any client-supplied
  role value.
- Admin and analyst accounts can only be created through the protected `POST /api/v1/users` endpoint, which
  requires `require_role(["admin"])`.
- JWT role claims are generated from the actual database user role, not client input.

**Verified via automated tests (`backend/tests/test_auth.py`, `backend/tests/test_rbac_and_security.py`):**
- Public registration with `role=admin` → account created with `role="user"`
- Public registration with `role=analyst` → account created with `role="user"`
- Public registration with no role field → account created with `role="user"`
- Unauthenticated `POST /api/v1/users` → 401
- Analyst attempting `POST /api/v1/users` with `role=admin` → 403
- Admin creating admin account via `POST /api/v1/users` → 201, role="admin"
- Admin creating analyst account via `POST /api/v1/users` → 201, role="analyst"

## What is deliberately never stored
Real card numbers, CVVs, OTPs, or real banking credentials — anywhere in this codebase, including test fixtures
and the simulator. All transaction data is fabricated/synthetic (see `docs/dataset_choice.md`).
