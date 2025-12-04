# Step 03 – Auth Foundation

## Goal
Implement the user domain (models, schemas, security helpers) and the Auth blueprint so registration/login flows are functional, matching `项目计划` sections 4.1 and 7.1.

## Dependencies
- Step 02 (app factory, extensions, blueprint stubs)

## Detailed Tasks
1. Define `sat_app/models/user.py` with `User` (id, email, password_hash, role, created_at) and `UserProfile` (OneToOne with `User`, target scores, exam date, daily minutes, language preference).
2. Add a `sat_app/utils/security.py` helper for password hashing/verification (e.g., wrap `werkzeug.security`), plus JWT identity helpers if needed.
3. Create Marshmallow/Pydantic schemas in `sat_app/schemas/user_schema.py` for request validation and response serialization.
4. Flesh out `sat_app/blueprints/auth_bp.py`:
   - `POST /api/auth/register` (validate payload, hash password, create user/profile, return JWT).
   - `POST /api/auth/login` (verify credentials, issue JWT with role claims).
   - Optional `/api/auth/me` to return current user data using JWT identity.
5. Centralize error handling (duplicate email, weak password) and return consistent JSON structures.
6. Configure Flask-JWT-Extended in `create_app` (token locations, expiration, callback for loading users).
7. Write unit tests covering registration, login, and profile defaults.
8. Update `README.md` with instructions for obtaining tokens and testing endpoints (e.g., curl/Postman snippets).

## Deliverables
- Working `User` + `UserProfile` models and migrations-ready schemas.
- Auth routes issuing JWTs and persisting user data.
- Tests demonstrating happy path and failure modes.

## Verification
- `pytest sat_app/tests/test_auth.py` passes.
- Manual `curl` against `/api/auth/register` and `/api/auth/login` returns expected JSON and tokens.
- Database shows newly created users with hashed passwords (no plaintext storage).

## Notes
- Keep business logic lean; multi-role access control can be expanded in later steps once other blueprints exist.

