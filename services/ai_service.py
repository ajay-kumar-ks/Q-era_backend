"""
AI service â€” Google Gemini integration with dynamic API-key rotation.

Uses google-generativeai SDK to call Gemini models for:
- Duplicate question detection
- Tag suggestion
- Difficulty analysis
- Content moderation
- Semantic search (future phases)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from google.api_core import exceptions as google_exceptions

try:
    from backend.config import get_api_key_manager
except ImportError:
    from config import get_api_key_manager

logger = logging.getLogger("ai_service")

# Primary model and ordered fallbacks — if one hits quota, we try the next
MODEL_CANDIDATES = [
    "gemini-2.5-flash",        # latest, generous free tier
    "gemini-2.0-flash-lite",   # fallback: highest RPM on free tier
    "gemini-2.0-flash",        # fallback
]
MODEL_NAME = MODEL_CANDIDATES[0]

# Safety settings â€” block high-severity harm, allow everything else
SAFETY_SETTINGS = [
    {"category": HarmCategory.HARM_CATEGORY_HARASSMENT, "threshold": HarmBlockThreshold.BLOCK_ONLY_HIGH},
    {"category": HarmCategory.HARM_CATEGORY_HATE_SPEECH, "threshold": HarmBlockThreshold.BLOCK_ONLY_HIGH},
    {"category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, "threshold": HarmBlockThreshold.BLOCK_ONLY_HIGH},
    {"category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, "threshold": HarmBlockThreshold.BLOCK_ONLY_HIGH},
]

GENERATION_CONFIG = {
    "temperature": 0.4,
    "top_p": 0.9,
    "top_k": 40,
    "max_output_tokens": 1024,
}


def _call_model(prompt: str, generation_config: dict | None = None) -> dict[str, Any] | None:
    """
    Call Gemini synchronously, rotating through all API keys × all MODEL_CANDIDATES.

    Strategy: try every (key, model) combination until one succeeds.
    On 429 — mark that key as failed for this model, try next key with same model.
    On 403 — key is invalid entirely, skip it for all models.
    NOTE: Always call via _call_model_async from async code.
    """
    manager = get_api_key_manager()
    cfg = generation_config or GENERATION_CONFIG

    # Collect all available keys upfront
    all_keys = manager.active_keys
    if not all_keys:
        logger.warning("No Google AI API keys configured - AI features disabled.")
        return None

    for model_name in MODEL_CANDIDATES:
        # Try every key for this model
        for key in all_keys:
            # Skip if this key is currently in cooldown
            if manager.get_key() is None:
                break  # all keys exhausted

            for attempt in range(2):
                try:
                    genai.configure(api_key=key)
                    model = genai.GenerativeModel(
                        model_name=model_name,
                        safety_settings=SAFETY_SETTINGS,
                        generation_config=cfg,
                    )
                    response = model.generate_content(prompt)
                    if not response.candidates:
                        logger.warning("Gemini (%s) returned no candidates.", model_name)
                        break  # try next key

                    text = response.text or ""
                    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
                    text = re.sub(r"\s*```$", "", text)
                    result = json.loads(text)
                    manager.mark_succeeded(key)
                    return result

                except google_exceptions.ResourceExhausted as exc:
                    logger.warning("Key %.12s... / Model %s rate-limited (429)", key, model_name)
                    manager.mark_failed(key)
                    break  # try next key for same model

                except google_exceptions.PermissionDenied as exc:
                    logger.warning("Key %.12s... rejected (403): %s", key, str(exc)[:80])
                    manager.mark_failed(key)
                    break  # try next key

                except (json.JSONDecodeError, ValueError) as exc:
                    logger.warning("Gemini (%s) non-JSON response: %s", model_name, exc)
                    if attempt == 0:
                        continue
                    break

                except Exception as exc:
                    logger.warning("Gemini (%s) key %.12s... error: %s", model_name, key, str(exc)[:120])
                    if attempt == 0:
                        continue
                    break

    logger.error("All key × model combinations exhausted - no response.")
    return None


async def _call_model_async(prompt: str, generation_config: dict | None = None) -> dict[str, Any] | None:
    """
    Async wrapper: runs the blocking _call_model in a thread executor so it
    never blocks the FastAPI event loop.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _call_model, prompt, generation_config)


# ---------------------------------------------------------------------------
# Phase 1: Real AI functions
# ---------------------------------------------------------------------------


async def check_duplicate(db, title: str, description: str | None) -> dict[str, Any]:
    """
    Ask Gemini whether a question with the same title/description already exists.

    Fetches up to 200 existing question titles + IDs from the DB and sends them
    to Gemini so it can detect semantic/near duplicates, not just exact matches.
    Falls back to a DB keyword scan if the AI call fails.
    """
    # Fetch existing question titles to give Gemini context
    existing_titles_text = ""
    existing_rows: list[tuple] = []
    if db is not None:
        try:
            cursor = await db.execute(
                "SELECT id, title FROM questions WHERE is_flagged = 0 ORDER BY created_at DESC LIMIT 200"
            )
            existing_rows = await cursor.fetchall()
            if existing_rows:
                lines = [f"[{r[0]}] {r[1]}" for r in existing_rows]
                existing_titles_text = "\n".join(lines)
        except Exception as exc:
            logger.warning("Could not fetch existing questions for duplicate check: %s", exc)

    if existing_titles_text:
        prompt = f"""You are a duplicate-detection assistant for a Q&A platform.
Analyze the new question below and decide if any existing question is semantically similar
(same meaning, just rephrased â€” not just identical wording).

New question:
  Title: {title}
  Description: {description or 'N/A'}

Existing questions (format: [id] title):
{existing_titles_text}

Return JSON with exactly these keys:
- is_duplicate (boolean): true if a semantically similar question exists
- similar_ids (array of ints): IDs of similar existing questions (max 3, empty if none)
- confidence (float 0.0-1.0): your confidence in the assessment
- reason (string): brief explanation if duplicate, otherwise empty string

Output ONLY valid JSON, no markdown, no extra text."""
    else:
        prompt = f"""You are a duplicate-detection assistant for a Q&A platform.
Analyze the following question and decide whether it is likely a duplicate.

Title: {title}
Description: {description or 'N/A'}

Return JSON with exactly these keys:
- is_duplicate (boolean): true if likely duplicate, false otherwise
- similar_ids (array of ints): empty array
- confidence (float 0.0-1.0): your confidence in the assessment
- reason (string): short explanation if duplicate, otherwise empty string

Output ONLY valid JSON, no markdown, no extra text."""

    result = await _call_model_async(prompt)
    if result is not None and "is_duplicate" in result:
        return {
            "is_duplicate": result.get("is_duplicate", False),
            "similar_ids": result.get("similar_ids", []),
            "confidence": result.get("confidence", 0.0),
            "reason": result.get("reason", ""),
        }

    # Fallback: basic DB keyword scan
    if db is not None:
        try:
            like_title = f"%{title}%"
            query = "SELECT id, title FROM questions WHERE title LIKE ? OR description LIKE ? LIMIT 3"
            cursor = await db.execute(query, (like_title, like_title))
            rows = await cursor.fetchall()
            matches = [{"id": r[0], "title": r[1]} for r in rows]
            return {
                "is_duplicate": len(matches) > 0,
                "similar_ids": [m["id"] for m in matches],
                "confidence": 0.7 if matches else 0.0,
                "reason": "Fallback DB keyword scan" if matches else "",
            }
        except Exception as exc:
            logger.warning("Fallback duplicate scan failed: %s", exc)

    return {"is_duplicate": False, "similar_ids": [], "confidence": 0.0, "reason": ""}


async def suggest_tags(db, title: str, description: str | None) -> list[str]:
    """
    Ask Gemini to suggest up to 5 relevant tags for a question.
    Falls back to keyword matching if AI fails.
    """
    prompt = f"""You are a tagging assistant for an educational Q&A platform.
Suggest up to 5 relevant tags (lowercase, single words or short phrases) for this question.

Title: {title}
Description: {description or 'N/A'}

Return JSON: {{"tags": ["tag1", "tag2", ...]}}
Output ONLY valid JSON, no markdown, no extra text."""

    result = await _call_model_async(prompt)
    if result is not None and isinstance(result.get("tags"), list):
        return result["tags"][:5]

    # Fallback: keyword matching
    text = f"{title} {description or ''}".lower()
    suggestions = []
    mappings = {
        "math": ["math", "equation", "algebra", "calculus", "geometry"],
        "science": ["science", "physics", "chemistry", "biology", "planet"],
        "history": ["history", "year", "century", "ancient", "modern"],
        "programming": ["programming", "code", "python", "java", "algorithm"],
        "english": ["english", "grammar", "vocabulary", "literature"],
    }
    for tag, keywords in mappings.items():
        if any(kw in text for kw in keywords):
            suggestions.append(tag)
    return suggestions or ["general"]


async def analyze_difficulty(db, title: str, description: str | None) -> dict[str, Any]:
    """
    Ask Gemini to classify difficulty as 'easy', 'medium', or 'hard'.
    Falls back to keyword heuristic if AI fails.
    """
    prompt = f"""You are a difficulty-rating assistant for educational questions.
Classify this question as 'easy', 'medium', or 'hard'.

Title: {title}
Description: {description or 'N/A'}

Return JSON: {{"difficulty": "easy|medium|hard", "confidence": 0.0-1.0}}
Output ONLY valid JSON, no markdown, no extra text."""

    result = await _call_model_async(prompt)
    if result is not None and result.get("difficulty") in ("easy", "medium", "hard"):
        return {"difficulty": result["difficulty"], "confidence": result.get("confidence", 0.8)}

    # Fallback: keyword heuristic
    text = f"{title} {description or ''}".lower()
    easy_words = {"basic", "simple", "easy", "beginner", "elementary"}
    hard_words = {"hard", "difficult", "complex", "advanced", "expert", "challenging"}
    if any(w in text for w in easy_words):
        return {"difficulty": "easy", "confidence": 0.85}
    if any(w in text for w in hard_words):
        return {"difficulty": "hard", "confidence": 0.8}
    return {"difficulty": "medium", "confidence": 0.7}


async def moderation_filter(text: str) -> dict[str, Any]:
    """
    Ask Gemini to check text for toxicity, spam, or inappropriate content.
    """
    if not text or len(text.strip()) < 3:
        return {"is_toxic": False, "is_spam": False, "reason": None}

    prompt = f"""You are a content moderation assistant. Analyze the following text
for toxicity, spam, harassment, or any policy violations.

Text: \"{text}\"

Return JSON:
{{
  "is_toxic": false,
  "is_spam": false,
  "reason": null
}}

Output ONLY valid JSON, no markdown, no extra text."""

    result = await _call_model_async(prompt)
    if result is not None:
        return {
            "is_toxic": result.get("is_toxic", False),
            "is_spam": result.get("is_spam", False),
            "reason": result.get("reason"),
        }

    # Fallback: simple keyword block
    blocked = ["spam", "buy now", "click here", "free money", "casino", "xxx"]
    lower = text.lower()
    if any(b in lower for b in blocked):
        return {"is_toxic": False, "is_spam": True, "reason": "Keyword match"}
    return {"is_toxic": False, "is_spam": False, "reason": None}


async def semantic_search(db, query: str) -> list[dict[str, Any]] | None:
    """
    Semantic search: fetch question titles from DB, ask Gemini to rank them by
    relevance to the natural-language query, and return the ranked question data.

    Returns a list of question dicts (id, title, description, score) sorted by
    descending relevance, or None if AI is unavailable (callers fall back to FTS).
    """
    if db is None:
        return None

    # Fetch up to 300 question titles to rank
    try:
        cursor = await db.execute(
            """SELECT id, title, description
               FROM questions
               WHERE is_public = 1 AND is_flagged = 0
               ORDER BY created_at DESC
               LIMIT 300"""
        )
        rows = await cursor.fetchall()
    except Exception as exc:
        logger.warning("semantic_search: DB fetch failed: %s", exc)
        return None

    if not rows:
        return None

    # Build a compact representation for Gemini
    question_lines = "\n".join(
        f"[{r[0]}] {r[1]}" + (f" - {r[2][:80]}" if r[2] else "")
        for r in rows
    )

    # Strip trailing noise words like "questions", "quiz", "problems" that users
    # habitually append but which confuse topic-matching in Gemini
    clean_query = re.sub(
        r'\b(questions?|quiz(?:zes)?|problems?|exercises?|examples?|topics?)\b',
        '',
        query,
        flags=re.IGNORECASE,
    ).strip()
    search_topic = clean_query if clean_query else query

    prompt = f"""You are a search-relevance ranker for an educational Q&A database.

TASK: Given a search topic, find the questions in the list below that are about that topic.
Do NOT generate new questions. Do NOT explain anything. ONLY rank existing questions by relevance.

Search topic: {search_topic}
(Original user query: {query})

Questions list (format: [id] title - description snippet):
{question_lines}

Instructions:
- Treat the search topic as a subject area, not a literal phrase to match.
- A question is relevant if its subject matter overlaps with the search topic.
- Include any question that is at least somewhat related.
- Score 1.0 = perfect match, 0.5 = related, 0.1 = loosely related.
- Return at most 20 results, sorted by score descending.
- If nothing is relevant, return an empty results array.

Return ONLY this JSON, no markdown, no explanation:
{{"results": [{{"id": <int>, "score": <float>}}, ...]}}"""

    result = await _call_model_async(prompt)
    if result is None or not isinstance(result.get("results"), list):
        return None

    ranked = result["results"]
    if not ranked:
        return None

    # Build a lookup from the fetched rows
    row_map: dict[int, tuple] = {r[0]: r for r in rows}

    output = []
    for item in ranked:
        qid = item.get("id")
        score = item.get("score", 0.0)
        if qid in row_map:
            r = row_map[qid]
            output.append({
                "id": r[0],
                "title": r[1],
                "description": r[2],
                "relevance_score": score,
            })

    return output if output else None






# ---------------------------------------------------------------------------
# Phase 2.1 — AI Question Generation
# ---------------------------------------------------------------------------

async def generate_questions(
    topic: str,
    q_type: str,
    difficulty: str,
    count: int,
) -> list[dict[str, Any]]:
    """
    Ask Gemini to generate `count` complete questions on `topic`.

    Returns a list of question dicts ready for DB insertion, or raises
    a ValueError with a user-friendly message if generation fails.
    """
    type_instructions = {
        "mcq": (
            "Multiple choice question with exactly 4 options. "
            "The 'options' array must have 4 items. "
            "'correct_answer' must exactly match the text of one option."
        ),
        "true_false": (
            "True/False question. "
            "'options' must be exactly: [{\"option_text\": \"True\", \"option_order\": 1}, "
            "{\"option_text\": \"False\", \"option_order\": 2}]. "
            "'correct_answer' must be either 'True' or 'False'."
        ),
        "short_answer": (
            "Short answer question. 'options' must be an empty array []. "
            "'correct_answer' is a concise expected answer (1–2 sentences)."
        ),
        "descriptive": (
            "Descriptive/essay question. 'options' must be an empty array []. "
            "'correct_answer' is a model answer (2–4 sentences)."
        ),
    }

    prompt = f"""You are an expert educational question author.
Generate exactly {count} {difficulty} {q_type} question(s) about: "{topic}"

Question type rules:
{type_instructions.get(q_type, '')}

For EACH question return a JSON object with these exact keys:
- "title": string — the question text (clear, unambiguous)
- "description": string or null — extra context / scenario if needed
- "type": "{q_type}"
- "difficulty": "{difficulty}"
- "correct_answer": string — the correct answer
- "explanation": string — why this is the correct answer (2–3 sentences)
- "tags": array of 2–4 lowercase tag strings relevant to the topic
- "options": array of option objects, each with "option_text" (string) and "option_order" (int starting at 1)

Return ONLY a JSON array of exactly {count} question object(s).
No markdown, no extra text, no numbering — just the raw JSON array.

Example structure:
[
  {{
    "title": "...",
    "description": null,
    "type": "{q_type}",
    "difficulty": "{difficulty}",
    "correct_answer": "...",
    "explanation": "...",
    "tags": ["tag1", "tag2"],
    "options": [{{"option_text": "...", "option_order": 1}}, ...]
  }}
]"""

    # Use higher token limit for generation — rotate through models automatically
    generation_cfg = {
        "temperature": 0.7,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 4096,
    }
    raw = await _call_model_async(prompt, generation_cfg)
    if raw is None:
        raise ValueError("AI generation is currently unavailable. Please try again or create questions manually.")

    # Normalise — Gemini sometimes wraps in {"questions": [...]}
    if isinstance(raw, dict):
        raw = raw.get("questions") or raw.get("results") or []

    if not isinstance(raw, list) or len(raw) == 0:
        raise ValueError("AI returned an unexpected response format. Please try again.")

    # Validate and sanitize each question
    valid = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if len(title) < 5:
            continue
        correct_answer = str(item.get("correct_answer") or "").strip()
        if not correct_answer:
            continue

        options_raw = item.get("options") or []
        options = []
        for i, opt in enumerate(options_raw):
            if isinstance(opt, dict) and opt.get("option_text"):
                options.append({
                    "option_text": str(opt["option_text"]).strip(),
                    "option_order": int(opt.get("option_order", i + 1)),
                })

        # For MCQ enforce at least 2 options
        if q_type == "mcq" and len(options) < 2:
            continue

        tags = [str(t).lower().strip() for t in (item.get("tags") or []) if t][:5]
        if not tags:
            tags = [topic.lower().split()[0]]

        valid.append({
            "title": title,
            "description": str(item.get("description") or "").strip() or None,
            "type": q_type,
            "difficulty": difficulty,
            "correct_answer": correct_answer,
            "explanation": str(item.get("explanation") or "").strip() or None,
            "tags": tags,
            "options": options,
        })

    if not valid:
        raise ValueError("AI did not generate any valid questions. Please try a different topic or type.")

    return valid






# ---------------------------------------------------------------------------
# Phase 2.2 — AI Exam Generation
# ---------------------------------------------------------------------------

async def generate_exam(
    topic: str,
    difficulty_mix: dict,   # {"easy": int, "medium": int, "hard": int}
    types: list[str],
    question_count: int,
) -> dict:
    """
    Ask Gemini to generate a full exam specification:
    - An exam title and description
    - `question_count` questions matching the difficulty_mix and types

    Returns a dict with keys: title, description, questions[]
    Each question has the same shape as generate_questions() output.
    Raises ValueError on failure.
    """
    easy_n = difficulty_mix.get("easy", 0)
    medium_n = difficulty_mix.get("medium", 0)
    hard_n = difficulty_mix.get("hard", 0)

    # Clamp to question_count if mix doesn't add up
    total_mix = easy_n + medium_n + hard_n
    if total_mix == 0:
        medium_n = question_count
        total_mix = question_count
    elif total_mix != question_count:
        # Scale proportionally
        factor = question_count / total_mix
        easy_n = round(easy_n * factor)
        hard_n = round(hard_n * factor)
        medium_n = question_count - easy_n - hard_n

    types_str = ", ".join(types) if types else "mcq"

    type_rules = {
        "mcq": "4 options, correct_answer matches one option exactly",
        "true_false": "options: [{option_text: 'True', option_order: 1}, {option_text: 'False', option_order: 2}], correct_answer is 'True' or 'False'",
        "short_answer": "options: [], correct_answer is a short expected answer",
        "descriptive": "options: [], correct_answer is a model answer",
    }
    type_rules_str = "\n".join(f"  - {t}: {type_rules.get(t, '')}" for t in types)

    prompt = f"""You are an expert exam author for an educational platform.
Create a complete exam on the topic: "{topic}"

Exam requirements:
- Total questions: {question_count}
- Difficulty breakdown: {easy_n} easy, {medium_n} medium, {hard_n} hard
- Question types to use (rotate through them): {types_str}

Type-specific rules:
{type_rules_str}

For EACH question include these fields:
- "title": string (the question)
- "description": string or null (extra context if needed)
- "type": one of [{types_str}]
- "difficulty": "easy", "medium", or "hard"
- "correct_answer": string
- "explanation": string (2-3 sentences why this is correct)
- "tags": array of 2-3 lowercase tag strings
- "options": array of {{"option_text": string, "option_order": int}} — follow type rules above

Return ONLY this JSON structure, no markdown, no extra text:
{{
  "title": "descriptive exam title here",
  "description": "brief overview of what this exam covers",
  "questions": [ ...array of {question_count} question objects... ]
}}"""

    generation_cfg = {
        "temperature": 0.7,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 8192,
    }

    raw = await _call_model_async(prompt, generation_cfg)

    if raw is None:
        raise ValueError("AI generation is currently unavailable. Please try again or create the exam manually.")

    if not isinstance(raw, dict):
        raise ValueError("AI returned an unexpected response format. Please try again.")

    # Extract fields
    exam_title = str(raw.get("title") or f"AI-Generated Exam: {topic}").strip()
    exam_description = str(raw.get("description") or "").strip() or None
    raw_questions = raw.get("questions") or []

    if not isinstance(raw_questions, list) or len(raw_questions) == 0:
        raise ValueError("AI did not generate any questions. Please try a different topic.")

    # Validate questions (reuse same logic as generate_questions)
    valid = []
    for item in raw_questions:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if len(title) < 5:
            continue
        correct_answer = str(item.get("correct_answer") or "").strip()
        if not correct_answer:
            continue
        q_type = str(item.get("type") or types[0])
        if q_type not in ("mcq", "true_false", "short_answer", "descriptive"):
            q_type = types[0]
        difficulty = str(item.get("difficulty") or "medium")
        if difficulty not in ("easy", "medium", "hard"):
            difficulty = "medium"

        options_raw = item.get("options") or []
        options = []
        for i, opt in enumerate(options_raw):
            if isinstance(opt, dict) and opt.get("option_text"):
                options.append({
                    "option_text": str(opt["option_text"]).strip(),
                    "option_order": int(opt.get("option_order", i + 1)),
                })

        if q_type == "mcq" and len(options) < 2:
            continue

        tags = [str(t).lower().strip() for t in (item.get("tags") or []) if t][:5]
        if not tags:
            tags = [topic.lower().split()[0]]

        valid.append({
            "title": title,
            "description": str(item.get("description") or "").strip() or None,
            "type": q_type,
            "difficulty": difficulty,
            "correct_answer": correct_answer,
            "explanation": str(item.get("explanation") or "").strip() or None,
            "tags": tags,
            "options": options,
        })

    if not valid:
        raise ValueError("AI did not generate any valid questions. Please try a different topic or type.")

    return {
        "title": exam_title,
        "description": exam_description,
        "questions": valid,
    }


# ---------------------------------------------------------------------------
# Phase 2.3 — AI Answer Explanation
# ---------------------------------------------------------------------------

async def explain_answer(
    question_title: str,
    question_description: str | None,
    correct_answer: str,
    user_answer: str | None,
    is_correct: bool | None,
) -> dict:
    """
    Ask Gemini to explain why an answer is correct or incorrect, identify the
    key concept being tested, and suggest what to study.

    Returns dict with: explanation, key_concept, suggestion
    Falls back to a plain message if AI is unavailable.
    """
    answered = user_answer and user_answer.strip()
    context = ""
    if question_description:
        context = f"\nContext / code:\n{question_description}\n"

    if is_correct is True or (answered and user_answer.strip().lower() == correct_answer.strip().lower()):
        verdict = "The student answered CORRECTLY."
        task = (
            "Briefly reinforce why this is correct. "
            "Mention the key concept being tested and a tip to remember it."
        )
    elif answered:
        verdict = f"The student answered INCORRECTLY. They chose: \"{user_answer.strip()}\""
        task = (
            "Explain clearly why their answer is wrong and why the correct answer is right. "
            "Identify the key concept they missed and suggest what to review."
        )
    else:
        verdict = "The student did not answer."
        task = (
            "Explain what the correct answer means and why it is correct. "
            "Identify the key concept and suggest what to study."
        )

    prompt = f"""You are a friendly educational AI tutor helping a student review their exam.

Question: {question_title}{context}
Correct answer: {correct_answer}
{verdict}

{task}

Return ONLY this JSON, no markdown, no extra text:
{{
  "explanation": "2-4 sentence explanation",
  "key_concept": "the concept or topic being tested (short phrase)",
  "suggestion": "one specific study suggestion"
}}"""

    result = await _call_model_async(prompt)

    if result and isinstance(result.get("explanation"), str):
        return {
            "explanation": result["explanation"].strip(),
            "key_concept": (result.get("key_concept") or "").strip() or None,
            "suggestion": (result.get("suggestion") or "").strip() or None,
        }

    # Fallback — return whatever static explanation the question has
    return {
        "explanation": "AI explanation is currently unavailable. Please try again later.",
        "key_concept": None,
        "suggestion": None,
    }
