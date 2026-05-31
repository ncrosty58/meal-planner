# Facade layer to maintain backwards compatibility for existing modules/scripts
import json
from .mealie_planner.mealie_client import MealieClient
from .mealie_planner.gemini_client import call_gemini, GeminiClient
from .mealie_planner.recipe_nutrition import calculate_nutrition_for_range
from .mealie_planner.recipe_crawler import RecipeCrawler, check_blackstone_compatibility
from .mealie_planner.plan_generator import PlanGenerator
from .mealie_planner.shopping_sync import ShoppingListSync
from .mealie_planner.email_notifier import EmailNotifier, send_email, send_daily_reminder_email
from .mealie_planner.parsers import parse_freezer_items, parse_exclusions
from .mealie_planner.utils import get_active_week_range, get_active_week_strings, sanitize_input

from .mealie_planner.config import (
    ACTIVE_LIST_ID,
    STAPLES_LIST_ID,
    RDA,
    TIMEZONE,
    APP_URL,
    FAMILY_RECIPIENT_EMAILS,
    FAMILY_NAMES,
    FAMILY_DIETARY_RULES_PROMPT,
    get_banned_recipes,
    _RECIPE_FINDER_SKILL_DEFINITION,
    _MEAL_EXCLUSION_PARSING_SKILL_DEFINITION,
    _WEEKLY_MEAL_SELECTION_SKILL_DEFINITION,
    _SHOPPING_LIST_SYNC_SKILL_DEFINITION,
    _RECIPE_NUTRITION_IMPUTATION_SKILL_DEFINITION,
    _BANNED_RECIPES_SKILL_DEFINITION,
    _INGREDIENT_PARSING_SKILL_DEFINITION
)

# Reusable client instances
_mealie_client = None
_gemini_client = None

def get_mealie_client():
    global _mealie_client
    if _mealie_client is None:
        _mealie_client = MealieClient()
    return _mealie_client

def get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = GeminiClient()
    return _gemini_client

def generate_weekly_plan(*args, **kwargs):
    client = get_mealie_client()
    gemini = get_gemini_client()
    generator = PlanGenerator(client, gemini)
    return generator.generate_weekly_plan(*args, **kwargs)

def sync_shopping_list(start_date_str, end_date_str, low_staples_ids=[], progress_callback=None, freezer_items=""):
    client = get_mealie_client()
    gemini = get_gemini_client()
    sync = ShoppingListSync(client, gemini)
    return sync.sync_shopping_list(start_date_str, end_date_str, low_staples_ids, progress_callback, freezer_items)
