# Step 09 – Learning Plan Service

## Goal
Generate personalized daily study plans using available time, exam timeline, and mastery gaps, following `项目计划` section 6.3.

## Dependencies
- Step 08 (mastery data and adaptive engine)

## Detailed Tasks
1. Ensure `UserProfile` contains `daily_available_minutes`, `target_score_rw`, `target_score_math`, and exam date (already defined in Step 03); add migrations if fields changed.
2. Implement `StudyPlan` model (user_id, plan_date, target_minutes, target_questions, generated_detail JSON).
3. Create `sat_app/services/learning_plan_service.py` with `generate_daily_plan(user_id, date_today)`:
   - Fetch mastery priorities from the adaptive engine.
   - Estimate RW vs Math needs (`estimate_section_gap` helper).
   - Build plan blocks (time slots, focus areas, question counts) per the JSON sample in the project plan.
   - Persist or update the `StudyPlan` record for the date.
4. Add background job or scheduled command (e.g., Celery/RQ or simple cron) to generate plans nightly; expose manual trigger via CLI (`flask plan generate --user <id>`).
5. Expose endpoints in `learning_bp`:
   - `GET /api/learning/plan/today` → returns current day’s plan, generating on demand if absent.
   - `POST /api/learning/plan/regenerate` (optional) for manual refresh with reason logging.
6. Add schema validation for the `generated_detail` structure to ensure front-end rendering consistency.
7. Integrate plan highlights into session start responses (e.g., indicate which block the current session belongs to).
8. Write tests covering plan generation under varying user profiles (limited time, near exam, unbalanced skills).
9. Document API usage and include sample plan JSON in developer docs.

## Deliverables
- StudyPlan model, service, and API endpoints.
- Automated or manual job for daily plan generation.
- Tests verifying plan content and persistence.

## Verification
- Calling `GET /api/learning/plan/today` returns structured blocks aligned with user data.
- Updating a user’s available minutes or exam date changes the next plan generation.
- Tests pass with deterministic outputs based on mocked skill priorities.

## Notes
- Keep plan generation deterministic for a given input to simplify testing and debugging; randomness should be seeded or avoided.

