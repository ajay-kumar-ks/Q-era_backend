"""
Spaced Repetition Service
Implements the SM-2 (SuperMemo 2) algorithm for optimal review scheduling.
"""
from datetime import datetime, timedelta
from typing import Optional


def calculate_next_interval(
    review_count: int,
    ease_factor: float,
    previous_interval: int,
    quality: int,
) -> tuple[int, float]:
    """
    Calculate the next review interval and ease factor using SM-2 algorithm.
    
    Args:
        review_count: Number of times this item has been reviewed (0 for first time)
        ease_factor: Current ease factor (default 2.5, range 1.3 - 2.6)
        previous_interval: Days since last review
        quality: Quality of answer (0-5, where 5 is perfect, 0 is forgotten)
    
    Returns:
        Tuple of (next_interval_days, new_ease_factor)
    """
    # SM-2 Algorithm
    # Quality: 0-2 = incorrect, 3-5 = correct variants
    
    # Calculate new ease factor
    new_ease = ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    new_ease = max(1.3, min(2.6, new_ease))  # Clamp between 1.3 and 2.6
    
    # Calculate interval
    if quality < 3:  # Incorrect
        next_interval = 0
    elif review_count == 0:  # First review
        next_interval = 1
    elif review_count == 1:  # Second review
        next_interval = 3
    else:  # Subsequent reviews
        next_interval = max(1, int(previous_interval * new_ease))
    
    return next_interval, new_ease


def get_next_review_datetime(interval_days: int) -> str:
    """
    Get the ISO format datetime string for the next review.
    
    Args:
        interval_days: Number of days until next review
    
    Returns:
        ISO format datetime string
    """
    next_review = datetime.now() + timedelta(days=interval_days)
    return next_review.isoformat()


def get_priority_score(
    next_review_at: str,
    ease_factor: float,
    review_count: int,
) -> float:
    """
    Calculate a priority score for sorting review queue.
    Higher score = higher priority to review.
    
    Args:
        next_review_at: ISO format datetime string for next review
        ease_factor: Current ease factor
        review_count: Number of reviews completed
    
    Returns:
        Priority score (higher = more urgent)
    """
    try:
        next_dt = datetime.fromisoformat(next_review_at)
    except (ValueError, TypeError):
        return 0.0
    
    days_overdue = (datetime.now() - next_dt).days
    
    # Priority increases with days overdue and decreases with ease factor
    # Lower ease factor = more difficult = higher priority
    priority = max(0, days_overdue + 1) * (3.0 / ease_factor)
    
    return priority


def get_review_statistics(reviews: list[dict]) -> dict:
    """
    Calculate statistics from review history.
    
    Args:
        reviews: List of review history records
    
    Returns:
        Dictionary with statistics
    """
    if not reviews:
        return {
            "total_reviews": 0,
            "correct_count": 0,
            "incorrect_count": 0,
            "accuracy": 0.0,
            "average_time_seconds": 0,
        }
    
    total = len(reviews)
    correct = sum(1 for r in reviews if r.get("is_correct"))
    incorrect = total - correct
    avg_time = sum(r.get("time_spent_seconds", 0) for r in reviews) / total if total > 0 else 0
    
    return {
        "total_reviews": total,
        "correct_count": correct,
        "incorrect_count": incorrect,
        "accuracy": (correct / total * 100) if total > 0 else 0.0,
        "average_time_seconds": int(avg_time),
    }
