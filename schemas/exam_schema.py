from typing import Dict, List, Optional

from pydantic import BaseModel, Field, FieldValidationInfo, constr


class ExamQuestionCreate(BaseModel):
    question_id: int
    marks: int = Field(..., ge=1)
    question_order: Optional[int] = None


class ExamCreate(BaseModel):
    title: constr(min_length=5, max_length=255)
    description: Optional[str] = None
    duration_minutes: int = Field(..., ge=5)
    total_marks: int = Field(..., ge=1)
    is_public: Optional[bool] = True
    randomize_order: Optional[bool] = False
    randomize_options: Optional[bool] = False
    secure_mode: Optional[bool] = False
    scheduled_at: Optional[str] = None
    deadline: Optional[str] = None
    questions: List[ExamQuestionCreate] = Field(..., min_items=1)


class ExamUpdate(BaseModel):
    title: Optional[constr(min_length=5, max_length=255)] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = Field(None, ge=5)
    total_marks: Optional[int] = Field(None, ge=1)
    is_public: Optional[bool] = None
    randomize_order: Optional[bool] = None
    randomize_options: Optional[bool] = None
    secure_mode: Optional[bool] = None
    scheduled_at: Optional[str] = None
    deadline: Optional[str] = None
    questions: Optional[List[ExamQuestionCreate]] = None


class ExamQuestionOut(BaseModel):
    question_id: int
    title: str
    type: str
    difficulty: str
    marks: int
    question_order: int


class ExamOut(BaseModel):
    id: int
    user_id: int
    title: str
    description: Optional[str] = None
    duration_minutes: int
    total_marks: int
    is_public: bool
    randomize_order: bool
    randomize_options: bool
    secure_mode: bool
    scheduled_at: Optional[str] = None
    deadline: Optional[str] = None
    questions: List[ExamQuestionOut] = []
    created_at: str
    updated_at: str


class AttemptStart(BaseModel):
    id: int
    exam_id: int
    user_id: int
    attempt_number: int
    total_marks: int
    status: str
    started_at: str
    last_saved_at: str
    answers: Dict[str, str] = {}
    questions: List[ExamQuestionOut] = []


class AttemptSave(BaseModel):
    time_taken_seconds: int = Field(..., ge=0)
    answers: Dict[int, str]


class AttemptSubmit(BaseModel):
    attempt_id: int
    time_taken_seconds: int = Field(..., ge=0)
    answers: Dict[int, str]


class ResultOut(BaseModel):
    id: int
    exam_id: int
    user_id: int
    attempt_number: int
    score: int
    total_marks: int
    time_taken_seconds: int
    answers: Dict[str, str]
    questions: List[ExamQuestionOut] = []
    submitted_at: str


class UpcomingExamOut(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    user_id: int
    duration_minutes: int
    total_marks: int
    scheduled_at: Optional[str] = None
    deadline: Optional[str] = None
    is_public: bool
    secure_mode: bool

