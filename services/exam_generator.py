from typing import Any

try:
    from backend.models import exam_model
except ImportError:
    from models import exam_model


async def generate_exam(
    db,
    user_id: int,
    title: str,
    description: str | None,
    duration_minutes: int,
    total_marks: int,
    is_public: bool,
    randomize_order: bool,
    randomize_options: bool,
    secure_mode: bool,
    questions: list[dict[str, Any]],
) -> dict[str, Any]:
    # Stub exam generator: persist exam payload directly.
    return await exam_model.create_exam(
        db,
        user_id=user_id,
        title=title,
        description=description,
        duration_minutes=duration_minutes,
        total_marks=total_marks,
        is_public=is_public,
        randomize_order=randomize_order,
        randomize_options=randomize_options,
        secure_mode=secure_mode,
        questions=questions,
    )
