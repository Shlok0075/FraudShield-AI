# Security Guide (Week 14)

Implemented and ready to explain in the viva:

| Control | Implementation |
|---|---|
| Password hashing | bcrypt via passlib (`app/auth/security.py`) — never plaintext |
| JWT authentication | short-lived (60 min) access tokens, secret from `JWT_SECRET` env var, HS256 |
| Role-based access control | `require_role([...])` dependency, per-route (`app/auth/dependencies.py`) |
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

## What is deliberately never stored
Real card numbers, CVVs, OTPs, or real banking credentials — anywhere in this codebase, including test fixtures
and the simulator. All transaction data is fabricated/synthetic (see `docs/dataset_choice.md`).
