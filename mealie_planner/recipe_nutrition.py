import json
import requests
from datetime import datetime, timedelta

from .config import (
    RDA, BREAKFAST_PROFILES, LUNCH_LEFTOVER_PROFILE, LUNCH_SANDWICH_PROFILE,
    _RECIPE_NUTRITION_IMPUTATION_SKILL_DEFINITION
)

def parse_nutrient_val(val):
    if not val:
        return 0.0
    try:
        cleaned = "".join(c for c in str(val) if c.isdigit() or c == '.')
        return float(cleaned) if cleaned else 0.0
    except:
        return 0.0

class RecipeNutrition:
    def __init__(self, mealie_client, gemini_client):
        self.client = mealie_client
        self.gemini = gemini_client

    def impute_recipe_nutrition(self, recipe) -> dict:
        """Estimate and save missing or incomplete recipe nutrition information using the AI skill."""
        slug = recipe.get('slug')
        if not slug:
            return recipe
            
        print(f"[Nutrition Imputation] Triggering AI nutrition estimation for: {recipe.get('name')} (slug: {slug})")
        
        # Format ingredients & instructions for prompt
        ing_list = []
        for ing in recipe.get('recipeIngredient', []):
            ing_list.append(ing.get('display') or ing.get('note') or "")
        ingredients_str = "\n".join(ing_list)

        inst_list = []
        for inst in recipe.get('recipeInstructions', []):
            inst_list.append(inst.get('text') or "")
        instructions_str = "\n".join(inst_list)

        servings = recipe.get('recipeServings', 4) or 4

        prompt = (
            f"You are an expert in the 'Recipe Nutrition Imputation Skill'.\n\n"
            f"{_RECIPE_NUTRITION_IMPUTATION_SKILL_DEFINITION}\n\n"
            f"### CONTEXT FOR THIS INVOCATION:\n"
            f"Recipe Name: {recipe['name']}\n"
            f"Description: {recipe.get('description', '')}\n"
            f"Servings: {servings}\n\n"
            f"Ingredients:\n{ingredients_str}\n\n"
            f"Instructions:\n{instructions_str}\n"
        )
        
        try:
            ai_response = self.gemini.call(prompt, expect_json=True)
            nutrition_data = json.loads(ai_response)
            
            # Prepare the updated recipe with new nutrition
            updated_recipe = dict(recipe)
            existing_nut = recipe.get('nutrition') or {}
            updated_recipe['nutrition'] = {
                "calories": nutrition_data.get('calories') or existing_nut.get('calories'),
                "carbohydrateContent": nutrition_data.get('carbohydrateContent') or existing_nut.get('carbohydrateContent'),
                "cholesterolContent": nutrition_data.get('cholesterolContent') or existing_nut.get('cholesterolContent'),
                "fatContent": nutrition_data.get('fatContent') or existing_nut.get('fatContent'),
                "fiberContent": nutrition_data.get('fiberContent') or existing_nut.get('fiberContent'),
                "proteinContent": nutrition_data.get('proteinContent') or existing_nut.get('proteinContent'),
                "saturatedFatContent": existing_nut.get('saturatedFatContent') or "0",
                "sodiumContent": nutrition_data.get('sodiumContent') or existing_nut.get('sodiumContent'),
                "sugarContent": nutrition_data.get('sugarContent') or existing_nut.get('sugarContent'),
                "transFatContent": existing_nut.get('transFatContent'),
                "unsaturatedFatContent": existing_nut.get('unsaturatedFatContent')
            }
            
            # Save back to Mealie
            r_put = requests.put(f"{self.client.api_url}/api/recipes/{slug}", json=updated_recipe, headers=self.client.headers)
            if r_put.status_code == 200:
                print(f"[Nutrition Imputation] Successfully updated recipe '{slug}' nutrition.")
                return r_put.json()
            else:
                print(f"[Nutrition Imputation] Failed to PUT recipe update (status {r_put.status_code}): {r_put.text}")
        except Exception as e:
            print(f"[Nutrition Imputation] Error during AI nutrition imputation for '{slug}': {e}")
            
        return recipe

    def calculate_nutrition_for_range(self, start_date_str, end_date_str):
        """Calculate daily nutrient totals and weekly averages for the date range."""
        meal_plans = self.client.get_meal_plan(start_date_str, end_date_str)
        
        daily_nutrients = {}
        
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
        current_date = start_date
        while current_date <= end_date:
            d_str = current_date.strftime("%Y-%m-%d")
            daily_nutrients[d_str] = {
                "calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0,
                "fiber": 0.0, "sodium": 0.0, "sugar": 0.0, "cholesterol": 0.0
            }
            current_date += timedelta(days=1)
            
        category_totals = {
            "breakfast": {k: 0.0 for k in RDA},
            "lunch": {k: 0.0 for k in RDA},
            "dinner": {k: 0.0 for k in RDA}
        }
        category_counts = {
            "breakfast": 0,
            "lunch": 0,
            "dinner": 0
        }

        for item in meal_plans:
            d_str = item['date']
            if d_str not in daily_nutrients:
                continue
                
            entry_type = item['entryType']
            title = item.get('title') or ""
            recipe_id = item.get('recipeId')
            
            nutrients = {
                "calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0,
                "fiber": 0.0, "sodium": 0.0, "sugar": 0.0, "cholesterol": 0.0
            }
            
            is_active = False
            if entry_type == 'breakfast':
                is_active = bool(title and title.lower().strip() != 'skipped')
                if is_active:
                    matched = False
                    for k, profile in BREAKFAST_PROFILES.items():
                        if k.lower() in title.lower():
                            nutrients = profile
                            matched = True
                            break
                    if not matched and title:
                        nutrients = BREAKFAST_PROFILES["Toast with Jam"]
                        
            elif entry_type == 'lunch':
                is_active = bool(title and title.lower().strip() != 'skipped')
                if is_active:
                    title_lower = title.lower()
                    if "leftover" in title_lower or not title:
                        nutrients = LUNCH_LEFTOVER_PROFILE
                    elif "sandwich" in title_lower or "pb&j" in title_lower:
                        nutrients = LUNCH_SANDWICH_PROFILE
                    else:
                        nutrients = BREAKFAST_PROFILES["Yogurt with Granola"]
                        
            elif entry_type == 'dinner':
                is_active = bool(recipe_id is not None or (title and title.lower().strip() not in ('eating out', 'skipped', 'tbd', '')))
                if is_active:
                    if recipe_id:
                        try:
                            recipe = self.client.get_recipe_details(recipe_id)
                            db_nutrition = recipe.get('nutrition', {})
                            
                            # Check if nutrition is missing or incomplete
                            key_fields = ['calories', 'proteinContent', 'carbohydrateContent', 'fatContent', 'fiberContent', 'sodiumContent']
                            is_incomplete = False
                            if not db_nutrition:
                                is_incomplete = True
                            else:
                                is_incomplete = any(db_nutrition.get(f) is None or db_nutrition.get(f) == "" or db_nutrition.get(f) == 0 or db_nutrition.get(f) == "0" for f in key_fields)
                                
                            if is_incomplete:
                                recipe = self.impute_recipe_nutrition(recipe)
                                db_nutrition = recipe.get('nutrition', {})
                                
                            if db_nutrition:
                                nutrients = {
                                    "calories": parse_nutrient_val(db_nutrition.get('calories')),
                                    "protein": parse_nutrient_val(db_nutrition.get('proteinContent')),
                                    "carbs": parse_nutrient_val(db_nutrition.get('carbohydrateContent')),
                                    "fat": parse_nutrient_val(db_nutrition.get('fatContent')),
                                    "fiber": parse_nutrient_val(db_nutrition.get('fiberContent')),
                                    "sodium": parse_nutrient_val(db_nutrition.get('sodiumContent')),
                                    "sugar": parse_nutrient_val(db_nutrition.get('sugarContent')),
                                    "cholesterol": parse_nutrient_val(db_nutrition.get('cholesterolContent'))
                                }
                        except Exception as e:
                            print(f"Error fetching recipe nutrition for {recipe_id}: {e}")
                            
            for k in daily_nutrients[d_str]:
                daily_nutrients[d_str][k] += nutrients.get(k, 0.0)
                
            if is_active and entry_type in category_totals:
                category_counts[entry_type] += 1
                for k in RDA:
                    category_totals[entry_type][k] += nutrients.get(k, 0.0)
                    
        averages = {k: 0.0 for k in RDA}
        for k in RDA:
            avg_bf = (category_totals["breakfast"][k] / category_counts["breakfast"]) if category_counts["breakfast"] > 0 else 0.0
            avg_ln = (category_totals["lunch"][k] / category_counts["lunch"]) if category_counts["lunch"] > 0 else 0.0
            avg_dn = (category_totals["dinner"][k] / category_counts["dinner"]) if category_counts["dinner"] > 0 else 0.0
            
            averages[k] = round(avg_bf + avg_ln + avg_dn, 1)
            
        return daily_nutrients, averages
