# Step 10 – Analytics and Diagnostics

## Goal
Provide progress analytics, score prediction, and diagnostic reporting that blend statistical rules with AI-generated narratives, per `项目计划` sections 5.4 and 7.1/7.3.

## Dependencies
- Step 09 (mastery and study plans in place)

## Detailed Tasks
1. Extend `sat_app/models/analytics.py` (or similar) to store aggregated metrics (daily accuracy, predicted scores, skill breakdowns).
2. Implement `sat_app/services/score_predictor.py`:
   - Start with heuristic/IRT-lite calculations using question difficulty and mastery scores.
   - Output RW and Math score estimates plus confidence intervals.
3. Build `sat_app/services/ai_diagnostic.py` combining:
   - Statistical summary (correctness, difficulty trends).
   - LLM-generated narrative based on structured data (per section 5.4).
4. Populate `analytics_bp` with endpoints:
   - `GET /api/analytics/progress` (time-series data for charts).
   - `POST /api/ai/diagnose` (maybe under `ai_bp` but returns combined diagnostic report).
5. Hook analytics updates into session completion:
   - After each `StudySession`, update rolling metrics and recalculate predictions.
6. Cache diagnostic reports to avoid repeated LLM calls; allow regeneration on demand.
7. Write tests using mocked predictor/AI clients to ensure deterministic outputs.
8. Document response schemas so the front-end can render charts and narrative reports.
9. Ensure analytics respect user privacy and only expose data for the authenticated student.

## Deliverables
- Score predictor and diagnostic services with API exposure.
- Analytics data model capturing per-user trends.
- Tests validating predictor math and AI integration pathways.

## Verification
- Calling `/api/analytics/progress` returns chronological data based on logged sessions.
- `/api/ai/diagnose` produces JSON with both numeric estimates and narrative text.
- Predictive outputs respond sensibly to changes (e.g., simulated improvement increases predicted score).

## Notes
- Keep predictor formulas modular so future IRT upgrades or ML models can replace the heuristics without touching API contracts.

