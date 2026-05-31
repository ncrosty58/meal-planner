import json
from datetime import datetime, timedelta
from .config import (
    _INGREDIENT_PARSING_SKILL_DEFINITION,
    _MEAL_EXCLUSION_PARSING_SKILL_DEFINITION
)
from .exceptions import SkillParsingError

def parse_freezer_items(gemini_client, text: str) -> list:
    """Use Gemini to parse free-text freezer/pantry/fridge items into structured ingredient data."""
    if not text or not text.strip():
        return []
    
    prompt = (
        "You are an expert in the 'Ingredient Parsing Skill'.\n\n" +
        _INGREDIENT_PARSING_SKILL_DEFINITION +
        "\n\n### CONTEXT FOR THIS INVOCATION:\n" +
        f"User input: {text}\n\n" +
        "Return ONLY the JSON array as specified in the skill definition."
    )
    
    try:
        raw = gemini_client.call(prompt, expect_json=True)
        result = json.loads(raw)
        if isinstance(result, list):
            return result
        raise ValueError("AI did not return a list")
    except Exception as e:
        print(f"[AI] parse_freezer_items failed: {e} — falling back to simple split")
        # Fallback: simple comma split if AI fails
        return [{"raw": i.strip(), "core_ingredient": i.strip(), "has_meat": False} 
                for i in text.split(",") if i.strip()]

def parse_exclusions(gemini_client, text: str, start_date, end_date) -> dict:
    """Use Gemini to interpret a free-text description of which meals to skip."""
    if not text or not text.strip():
        return {}

    num_days = (end_date - start_date).days + 1
    week_dates = {
        (start_date + timedelta(days=i)).strftime("%A"): (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(num_days)
    }

    prompt = (
        """You are an expert in the 'Mealie Meal Exclusion Parsing Skill'.

""" +
        _MEAL_EXCLUSION_PARSING_SKILL_DEFINITION +
        """

### CONTEXT FOR THIS INVOCATION:
""" +
        f"User input: {text}\n" +
        f"Week dates: {', '.join(f'{d} ({dt})' for d, dt in week_dates.items())}.\n\n" +
        "Return ONLY the JSON object as specified in the skill definition."
    )

    try:
        raw = gemini_client.call(prompt, expect_json=True)
        result = json.loads(raw)
        valid_days = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}
        valid_meals = {"breakfast", "lunch", "dinner"}
        exclusions = {}
        for day, meals in result.items():
            if day in valid_days and isinstance(meals, list):
                cleaned_meals = [m for m in meals if m in valid_meals]
                if cleaned_meals:
                    exclusions[day] = cleaned_meals
        return exclusions
    except Exception as e:
        print(f"[AI] parse_exclusions failed: {e} — no exclusions applied")
        return {}
