from typing import Any

try:
    from backend.models.question_model import get_question_by_id
except ImportError:
    from models.question_model import get_question_by_id


async def check_duplicate(db, title: str, description: str | None) -> dict[str, Any]:
    query = "SELECT id, title, description FROM questions WHERE title = ? OR description = ? LIMIT 3"
    cursor = await db.execute(query, (title, description))
    rows = await cursor.fetchall()
    matches = [dict(id=row[0], title=row[1], description=row[2]) for row in rows]
    return {
        "is_duplicate": len(matches) > 0,
        "similar_ids": [row["id"] for row in matches] if matches else [],
        "confidence": 0.9 if matches else 0.0,
    }


async def suggest_tags(db, title: str, description: str | None) -> list[str]:
    title_lower = title.lower()
    suggestions = []
    if 'math' in title_lower or 'equation' in title_lower:
        suggestions.append('math')
    if 'planet' in title_lower or 'science' in title_lower:
        suggestions.append('science')
    if 'history' in title_lower or 'year' in title_lower:
        suggestions.append('history')
    if not suggestions:
        suggestions.append('general')
    return suggestions


async def analyze_difficulty(db, title: str, description: str | None) -> dict[str, Any]:
    text = f"{title} {description or ''}".lower()
    if any(word in text for word in ['easy', 'simple', 'basic']):
        return {'difficulty': 'easy', 'confidence': 0.9}
    if any(word in text for word in ['hard', 'difficult', 'complex']):
        return {'difficulty': 'hard', 'confidence': 0.85}
    return {'difficulty': 'medium', 'confidence': 0.75}


async def moderation_filter(text: str) -> dict[str, Any]:
    return {'is_toxic': False, 'is_spam': False, 'reason': None}


async def semantic_search(query: str) -> list[dict[str, Any]] | None:
    """
    Semantic search fallback using AI embeddings or similarity matching.
    Currently a stub returning None (no AI integration in this phase).
    
    In future phases, this would:
    - Convert query to embedding
    - Find similar question embeddings
    - Return ranked results by similarity score
    
    Args:
        query: Natural language search query
    
    Returns:
        List of question objects or None if no results
    """
    return None
