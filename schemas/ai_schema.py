"""Pydantic schemas for AI feature endpoints."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class DuplicateCheckRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None


class DuplicateCheckResponse(BaseModel):
    is_duplicate: bool
    confidence: float
    reason: str = ""
    similar_ids: list[int] = []


class TagSuggestionRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None


class TagSuggestionResponse(BaseModel):
    tags: list[str]


class DifficultyAnalysisRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None


class DifficultyAnalysisResponse(BaseModel):
    difficulty: str  # "easy" | "medium" | "hard"
    confidence: float


class ModerationRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)


class ModerationResponse(BaseModel):
    is_toxic: bool
    is_spam: bool
    reason: str | None = None


class AIHealthResponse(BaseModel):
    status: str
    keys_configured: int
    gemini_available: bool
    model: str


# ---------------------------------------------------------------------------
# Phase 2.1 — AI Question Generation
# ---------------------------------------------------------------------------

class GenerateQuestionsRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=200, description="Topic or subject to generate questions about")
    type: str = Field("mcq", pattern="^(mcq|true_false|short_answer|descriptive)$")
    difficulty: str = Field("medium", pattern="^(easy|medium|hard)$")
    count: int = Field(3, ge=1, le=10, description="Number of questions to generate (1–10)")
    is_public: bool = Field(True)


class GeneratedOptionOut(BaseModel):
    option_text: str
    option_order: int


class GeneratedQuestionOut(BaseModel):
    id: int
    title: str
    description: str | None = None
    type: str
    correct_answer: str
    difficulty: str
    explanation: str | None = None
    tags: list[str] = []
    options: list[GeneratedOptionOut] = []


class GenerateQuestionsResponse(BaseModel):
    created: int
    questions: list[GeneratedQuestionOut]


class RequestAIQuestionsRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=200)
    type: str = Field("mcq", pattern="^(mcq|true_false|short_answer|descriptive)$")
    difficulty: str = Field("medium", pattern="^(easy|medium|hard)$")
    count: int = Field(3, ge=1, le=10)
    note: str | None = Field(None, max_length=500, description="Optional note to admin")


class RequestAIQuestionsResponse(BaseModel):
    message: str
    request_id: int | None = None


# ---------------------------------------------------------------------------
# Phase 2.2 — AI Exam Generation
# ---------------------------------------------------------------------------

class DifficultyMix(BaseModel):
    easy: int = Field(0, ge=0)
    medium: int = Field(0, ge=0)
    hard: int = Field(0, ge=0)


class GenerateExamRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=200)
    question_count: int = Field(5, ge=1, le=20, description="Total questions in the exam")
    difficulty_mix: DifficultyMix = Field(
        default_factory=lambda: DifficultyMix(easy=2, medium=2, hard=1)
    )
    types: list[str] = Field(
        default_factory=lambda: ["mcq"],
        description="Question types to include",
    )
    duration_minutes: int = Field(30, ge=5, le=180)
    is_public: bool = True
    randomize_order: bool = False


class GenerateExamQuestionOut(BaseModel):
    question_id: int
    title: str
    type: str
    difficulty: str
    marks: int
    question_order: int


class GenerateExamResponse(BaseModel):
    id: int
    title: str
    description: str | None = None
    duration_minutes: int
    total_marks: int
    is_public: bool
    question_count: int
    questions: list[GenerateExamQuestionOut] = []


# ---------------------------------------------------------------------------
# Phase 2.3 — AI Answer Explanation
# ---------------------------------------------------------------------------

class ExplainRequest(BaseModel):
    question_id: int
    user_answer: str | None = Field(None, max_length=1000)
    is_correct: bool | None = None


class ExplainResponse(BaseModel):
    explanation: str
    key_concept: str | None = None
    suggestion: str | None = None

