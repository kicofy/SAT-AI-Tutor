# Step 01 – Project Bootstrap

## Goal
Lay down the repository skeleton, virtual environment, and shared conventions so later features plug in cleanly as described in `项目计划` sections 1–3.

## Dependencies
- None

## Detailed Tasks
1. Confirm Python 3.11+ availability; record the version in `.python-version` if using pyenv, and document prerequisites in `README.md`.
2. Create a dedicated virtual environment (`python -m venv .venv`) and add activation instructions to `README.md`.
3. Inside the repo root, create the `sat_platform/` directory matching the proposed hierarchy (`app.py`, `config.py`, `requirements.txt`, `.env.example`, `sat_app/`, `migrations/`).
4. Under `sat_app/`, scaffold empty packages: `__init__.py`, `extensions.py`, `models/`, `services/`, `blueprints/`, `schemas/`, `utils/`, `tasks/` (each with `__init__.py` placeholders).
5. Add placeholder docstrings or TODO comments in new modules describing their future responsibilities (align with sections 1.2 and 2 of `项目计划`).
6. Draft `requirements.txt` with baseline dependencies: Flask, Flask-JWT-Extended, Flask-Migrate, Flask-CORS, SQLAlchemy, python-dotenv, and any tooling you plan to use (black, isort, pytest, etc.).
7. Create `.env.example` documenting required keys (database URL, JWT secret, AI model name, AI key) without real secrets; update `.gitignore` to exclude `.env`, `.venv`, `__pycache__`, and migration caches.
8. Expand `README.md` with quickstart instructions (environment setup, installing dependencies, running `python app.py` placeholder, folder overview referencing `项目计划`).
9. Install dependencies inside the virtual environment (`pip install -r requirements.txt`) and capture versions if you want a lock file later.

## Deliverables
- Folder tree and placeholder modules mirroring the architecture blueprint.
- Reproducible environment instructions (`README.md`, `.env.example`, `.python-version` if applicable).
- Baseline dependency list validated by a successful install.

## Verification
- `which python` inside the venv points to the project-local interpreter.
- `python -c "import flask"` succeeds.
- `tree sat_platform -L 2` (or similar) shows the expected directories.

## Notes
- Keep files lightweight; real logic begins in later steps once the structure is stable.

