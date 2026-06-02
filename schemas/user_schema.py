from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, constr


class UserQuestionMini(BaseModel):
    id: int
    title: str
    difficulty: str
    created_at: str
    status: str = "approved"


class UserExamMini(BaseModel):
    id: int
    title: str
    duration_minutes: int
    total_marks: int
    created_at: str
    status: str = "approved"


class UserProfileStats(BaseModel):
    global_rank: Optional[int] = None
    exams_attended: int = 0
    exams_created: int = 0
    questions_created: int = 0
    accuracy: float = 0.0


class BadgeOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    icon_url: Optional[str] = None
    unlocked_at: Optional[str] = None


class UserProfileOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: str
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    preferred_topics: List[str] = []
    learning_goals: Optional[str] = None
    notification_preferences: dict = {}
    created_at: str
    updated_at: str
    stats: UserProfileStats
    recent_questions: List[UserQuestionMini] = []
    recent_exams: List[UserExamMini] = []


class UserUpdate(BaseModel):
    name: Optional[constr(min_length=2, max_length=100)] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    preferred_topics: Optional[List[constr(min_length=1, max_length=50)]] = None
    learning_goals: Optional[str] = None
    notification_preferences: Optional[dict] = None
