# Facade layer to maintain backwards compatibility for existing modules/scripts

from mealie_planner.mealie_client import MealieClient
from mealie_planner.gemini_client import call_gemini, GeminiClient
from mealie_planner.recipe_nutrition import RecipeNutrition, parse_nutrient_val
from mealie_planner.recipe_crawler import RecipeCrawler
from mealie_planner.email_notifier import EmailNotifier, send_daily_reminder_email
from mealie_planner.plan_generator import PlanGenerator
from mealie_planner.shopping_sync import ShoppingListSync

def impute_recipe_nutrition(recipe, client=None):
    if not client:
        client = MealieClient()
    gemini = GeminiClient()
    nutrition = RecipeNutrition(client, gemini)
    return nutrition.impute_recipe_nutrition(recipe)

def calculate_nutrition_for_range(start_date_str, end_date_str):
    client = MealieClient()
    gemini = GeminiClient()
    nutrition = RecipeNutrition(client, gemini)
    return nutrition.calculate_nutrition_for_range(start_date_str, end_date_str)

def find_recipe_for_ingredient(ingredient, all_recipes=None):
    client = MealieClient()
    gemini = GeminiClient()
    crawler = RecipeCrawler(client, gemini)
    return crawler.find_recipe_for_ingredient(ingredient, all_recipes)

def find_and_import_recipe(ingredient, existing_recipe_ids=[]):
    client = MealieClient()
    gemini = GeminiClient()
    crawler = RecipeCrawler(client, gemini)
    return crawler.find_and_import_recipe(ingredient, existing_recipe_ids)

def get_recipes_from_api():
    client = MealieClient()
    gemini = GeminiClient()
    crawler = RecipeCrawler(client, gemini)
    return crawler.get_recipes_from_api()

def get_recipes_from_db():
    client = MealieClient()
    gemini = GeminiClient()
    crawler = RecipeCrawler(client, gemini)
    return crawler.get_recipes_from_db()

def check_blackstone_compatibility(recipe):
    client = MealieClient()
    gemini = GeminiClient()
    crawler = RecipeCrawler(client, gemini)
    return crawler.check_blackstone_compatibility(recipe)

def send_email(subject, html_content):
    client = MealieClient()
    gemini = GeminiClient()
    notifier = EmailNotifier(client, gemini)
    return notifier.send_email(subject, html_content)

def send_saturday_report_email(*args, **kwargs):
    client = MealieClient()
    gemini = GeminiClient()
    notifier = EmailNotifier(client, gemini)
    return notifier.send_saturday_report_email(*args, **kwargs)

def generate_weekly_plan(*args, **kwargs):
    client = MealieClient()
    gemini = GeminiClient()
    generator = PlanGenerator(client, gemini)
    return generator.generate_weekly_plan(*args, **kwargs)

def parse_exclusions(text: str) -> dict:
    client = MealieClient()
    gemini = GeminiClient()
    generator = PlanGenerator(client, gemini)
    return generator.parse_exclusions(text)

def sync_shopping_list(*args, **kwargs):
    client = MealieClient()
    gemini = GeminiClient()
    sync = ShoppingListSync(client, gemini)
    return sync.sync_shopping_list(*args, **kwargs)

def tag_dirty_dozen(note):
    client = MealieClient()
    gemini = GeminiClient()
    sync = ShoppingListSync(client, gemini)
    return sync.tag_dirty_dozen(note)

# Expose skill definition constants for backward compatibility
from mealie_planner.config import (
    load_skill_md,
    _RECIPE_FINDER_SKILL_DEFINITION,
    _MEAL_EXCLUSION_PARSING_SKILL_DEFINITION,
    _WEEKLY_MEAL_SELECTION_SKILL_DEFINITION,
    _SHOPPING_LIST_SYNC_SKILL_DEFINITION,
    _RECIPE_NUTRITION_IMPUTATION_SKILL_DEFINITION,
    _BANNED_RECIPES_SKILL_DEFINITION
)
