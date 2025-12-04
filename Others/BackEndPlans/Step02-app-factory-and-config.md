# Step 02 – App Factory and Configuration

## Goal
Implement the Flask application factory, shared extensions, and configuration objects so every blueprint can hook in consistently (per `项目计划` section 3).

## Dependencies
- Step 01 (project structure, requirements, env files)

## Detailed Tasks
1. Flesh out `config.py` with `BaseConfig`, `DevConfig`, `ProdConfig` (fields: `SQLALCHEMY_DATABASE_URI`, `SQLALCHEMY_TRACK_MODIFICATIONS`, `JWT_SECRET_KEY`, `AI_MODEL_NAME`, `OPENAI_API_KEY`, `DEBUG`).
2. Implement `sat_app/extensions.py` instantiating `SQLAlchemy`, `Migrate`, `JWTManager`, `CORS`, and any future helpers (e.g., Marshmallow).
3. In `sat_app/__init__.py`, build `create_app(config_name=None)` that loads `DevConfig` by default, initializes extensions, and registers blueprint placeholders (`auth_bp`, `admin_bp`, `student_bp`, `question_bp`, `learning_bp`, `ai_bp`, `analytics_bp`).
4. Inside each blueprint module, define minimal Flask `Blueprint` objects with simple `/ping` routes returning JSON; this keeps registration code testable before real endpoints exist.
5. Update `app.py` to import `create_app`, instantiate `app = create_app()`, and include the standard `if __name__ == "__main__": app.run(debug=True)` guard.
6. Ensure `.env` loading happens early (e.g., via `python-dotenv` in `app.py` or the factory) so configuration reads environment variables rather than hard-coded values.
7. Add smoke tests or a simple `pytest` case ensuring `create_app` returns a Flask instance and that blueprint URLs are registered.
8. Document any new environment variables in `.env.example` and `README.md`.

## Deliverables
- Working app factory with extension initialization.
- Blueprint stubs that allow the server to start.
- Config file supporting development and production overrides.

## Verification
- `flask --app app run` (or `python app.py`) starts without import errors and exposes `/api/auth/ping`, etc.
- `pytest` (if configured) passes smoke tests.
- Environment variable overrides change behavior (e.g., toggling `DEBUG`).

## Notes
- Keep blueprint routes minimal; detailed logic arrives in later steps once models and services exist.

