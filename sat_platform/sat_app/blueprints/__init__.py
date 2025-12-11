"""REST API blueprints (auth, admin, learning, etc.)."""

from __future__ import annotations

from .admin_bp import admin_bp
from .ai_bp import ai_bp
from .analytics_bp import analytics_bp
from .auth_bp import auth_bp
from .learning_bp import learning_bp
from .question_bp import question_bp
from .student_bp import student_bp
from .metrics_bp import metrics_bp
from .diagnostic_bp import diagnostic_bp
from .support_bp import support_bp
from .membership_bp import membership_bp

BLUEPRINTS = (
    (auth_bp, "/api/auth"),
    (admin_bp, "/api/admin"),
    (student_bp, "/api/student"),
    (question_bp, "/api/question"),
    (learning_bp, "/api/learning"),
    (diagnostic_bp, "/api/diagnostic"),
    (ai_bp, "/api/ai"),
    (analytics_bp, "/api/analytics"),
    (support_bp, "/api/support"),
    (membership_bp, "/api/membership"),
    (metrics_bp, ""),
)

__all__ = [
    "BLUEPRINTS",
    "admin_bp",
    "ai_bp",
    "analytics_bp",
    "auth_bp",
    "learning_bp",
    "diagnostic_bp",
    "support_bp",
    "question_bp",
    "student_bp",
    "metrics_bp",
    "membership_bp",
]

