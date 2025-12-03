# Step 05 – Admin Question Management (Manual CRUD)

## Goal
Model the SAT question bank and provide administrator APIs for manual ingestion, editing, and retrieval before AI automation kicks in (`项目计划` sections 4.2 and 7.2).

## Dependencies
- Step 04 (database migrations infrastructure)

## Detailed Tasks
1. Define models in `sat_app/models/question.py`:
   - `Passage` (id, content_text, metadata JSON).
   - `Question` (section, sub_section, passage_id, stem_text, choices JSON, correct_answer, difficulty_level, irt params, skill_tags, timing metadata).
   - `QuestionSet` (name, description, type, source metadata).
2. Create Marshmallow/Pydantic schemas for question payloads (`sat_app/schemas/question_schema.py`).
3. Expand `sat_app/blueprints/admin_bp.py` with endpoints:
   - `POST /api/admin/questions` (manual creation, accepts structured JSON).
   - `GET /api/admin/questions` (paginated list with filters by section/skill/difficulty).
   - `GET /api/admin/questions/<id>` for detail.
   - `PUT /api/admin/questions/<id>` for edits.
   - `DELETE /api/admin/questions/<id>` (soft delete optional).
4. Enforce admin-only access via JWT role checks.
5. Handle file uploads minimally (optional) or store source references for later AI parsing.
6. Add service layer (`sat_app/services/question_service.py`) to keep blueprints thin (validation, deduping, search helpers).
7. Write unit/integration tests covering CRUD flows and role enforcement.
8. Update migrations to include new tables and apply them.
9. Document API usage in `README.md` or a dedicated docs section (request/response samples).

## Deliverables
- Question-related models, schemas, and migrations.
- Admin blueprint with secure CRUD endpoints.
- Tests validating creation, filtering, and authorization.

## Verification
- `pytest sat_app/tests/test_admin_questions.py` passes.
- Admin token can create/edit questions; student token is denied (403).
- Database shows inserted questions, including JSON fields for choices and tags.

## Notes
- Keep AI parsing out of scope here; focus on reliable manual workflows to unblock downstream features.

