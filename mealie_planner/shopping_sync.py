import time
import json
import re

from .config import (
    ACTIVE_LIST_ID, STAPLES_LIST_ID, FAMILY_DIETARY_RULES_PROMPT,
    _SHOPPING_LIST_SYNC_SKILL_DEFINITION
)
from .recipe_crawler import RecipeCrawler
from .exceptions import MealieAPIError, SkillParsingError

class ShoppingListSync:
    def __init__(self, mealie_client, gemini_client):
        self.client = mealie_client
        self.gemini = gemini_client
        self.crawler = RecipeCrawler(mealie_client, gemini_client)

    def sync_staples_only(self, low_staples_ids) -> bool:
        """Fast, deterministic sync of staples only. No AI, no clearing of recipes."""
        print("[Sync] Performing fast staples-only update...")
        try:
            staples = self.client.get_shopping_list_items(STAPLES_LIST_ID)
            active_items = self.client.get_shopping_list_items_for_list(ACTIVE_LIST_ID)
            low_ids_clean = {s_id.replace('-', '').lower() for s_id in low_staples_ids}
            staple_names = {s['note'].strip().lower(): s for s in staples}
            
            active_staple_notes = []
            active_notes_set = set()
            for item in active_items:
                note = item['note'].strip().lower()
                active_notes_set.add(note)
                if note in staple_names:
                    active_staple_notes.append(item)

            to_add = []
            for s in staples:
                if s['id'].replace('-', '').lower() in low_ids_clean:
                    if s['note'].strip().lower() not in active_notes_set:
                        to_add.append({
                            "shoppingListId": ACTIVE_LIST_ID,
                            "note": s['note'],
                            "quantity": s.get('quantity', 1.0),
                            "checked": False,
                            "labelId": s.get('labelId')
                        })

            to_delete_ids = []
            for item in active_staple_notes:
                master_staple = staple_names.get(item['note'].strip().lower())
                if master_staple:
                    m_id = master_staple['id'].replace('-', '').lower()
                    if m_id not in low_ids_clean:
                        to_delete_ids.append(item['id'])

            if to_delete_ids: self.client.delete_shopping_list_items_bulk(to_delete_ids)
            if to_add: self.client.add_shopping_list_items_bulk(to_add)
            return True
        except Exception as e:
            print(f"Error during fast staples sync: {e}")
            return False

    def sync_shopping_list(self, start_date_str, end_date_str, low_staples_ids=[], progress_callback=None, freezer_items="") -> bool:
        """Non-destructive sync using Multi-Tiered matching to protect checkmarks and staples."""
        print(f"Starting non-destructive sync for {start_date_str} to {end_date_str}...")
        if progress_callback: progress_callback("Sync started...", 90)
        
        try:
            time.sleep(1.0)
            
            # 1. Fetch current data
            meal_plans = self.client.get_meal_plan(start_date_str, end_date_str)
            staples = self.client.get_shopping_list_items(STAPLES_LIST_ID)
            active_items = self.client.get_shopping_list_items_for_list(ACTIVE_LIST_ID)
            
            staple_names_lower = {s['note'].strip().lower() for s in staples}
            low_ids_clean = {sid.replace('-', '').lower() for sid in low_staples_ids}
            low_staples_notes = [s['note'] for s in staples if s['id'].replace('-', '').lower() in low_ids_clean]

            # 2. Analyze current items for "Checkmark Memory"
            if progress_callback: progress_callback("Analyzing current progress...", 93)
            
            # Memory of what was checked
            checked_notes = set()    # Exact strings
            checked_entities = set() # Base food names
            checked_keywords = set() # Individual core words
            active_staple_notes = []
            
            if active_items:
                current_notes = [item.get('note', '') for item in active_items]
                current_parsed = self.client.parse_raw_ingredients(current_notes)
                
                for idx, item in enumerate(active_items):
                    p_ing = current_parsed[idx] if idx < len(current_parsed) else {}
                    food_name = (p_ing.get('food', {}) or {}).get('name', '').strip().lower()
                    note_lower = item.get('note', '').strip().lower()
                    
                    # Track staples currently on the list for AI protection
                    if food_name in staple_names_lower or note_lower in staple_names_lower:
                        active_staple_notes.append(item['note'])

                    if item.get('checked'):
                        checked_notes.add(note_lower)
                        if food_name: checked_entities.add(food_name)
                        # Keywords (e.g., "Chicken", "Cilantro")
                        keywords = [w for w in re.findall(r'\w+', note_lower) if len(w) > 3]
                        checked_keywords.update(keywords)

            # 3. Extract ingredients from scheduled recipes
            recipe_ids_to_fetch = set()
            meal_plan_mapping = []
            all_recipes_overview = self.crawler.get_recipes_from_db()
            
            for p in meal_plans:
                rid = p.get('recipeId')
                title = p.get('title') or ""
                if not rid and title:
                    if title.lower().strip() not in {"leftovers", "pb&j sandwich", "eating out", "skipped", "cereal & milk", "oats", "planned meal", "planned dinner"}:
                        rid = self.crawler.find_recipe_for_ingredient(title, all_recipes=all_recipes_overview)
                if rid: recipe_ids_to_fetch.add(rid)
                meal_plan_mapping.append((p, rid))

            print(f"[Sync] Bulk fetching details for {len(recipe_ids_to_fetch)} unique recipes.")
            details_map = self.client.get_recipes_details_bulk(list(recipe_ids_to_fetch))

            raw_recipe_ingredients = []
            for _, rid in meal_plan_mapping:
                if rid and rid in details_map:
                    r_details = details_map[rid]
                    if r_details:
                        for ing in r_details.get('recipeIngredient', []):
                            txt = ing.get('display') or ing.get('originalText') or ""
                            if txt.strip(): raw_recipe_ingredients.append(txt.strip())

            # 4. Call AI Skill
            if progress_callback: progress_callback("Generating optimized list...", 96)
            
            combined_low = list(set(low_staples_notes + active_staple_notes))
            all_labels = self.client.get_labels()
            label_name_to_id = {l['name']: l['id'] for l in all_labels}

            payload = {
                "ingredients": raw_recipe_ingredients,
                "staples": [s['note'] for s in staples],
                "inventory_items": [i.strip() for i in freezer_items.split(",")] if freezer_items else [],
                "low_staples": combined_low,
                "available_labels": [l['name'] for l in all_labels]
            }
            
            prompt = f"You are an expert in 'Shopping List Sync Skill'.\n\n{_SHOPPING_LIST_SYNC_SKILL_DEFINITION}\n\n### CONTEXT:\nInput: {json.dumps(payload)}\nDietary: {FAMILY_DIETARY_RULES_PROMPT}\n\nReturn ONLY JSON."
            ai_response = self.gemini.call(prompt, expect_json=True)
            final_items = json.loads(ai_response)

            # 5. Smart Merge with Multi-Tiered Matching
            if progress_callback: progress_callback("Merging changes...", 98)
            
            new_item_names = [item.get('name', 'Unknown') for item in final_items]
            new_parsed = self.client.parse_raw_ingredients(new_item_names)
            
            to_add, to_update, matched_ids = [], [], set()

            for idx, ai_item in enumerate(final_items):
                name, qty, unit = ai_item.get('name', 'Unknown'), ai_item.get('quantity', 1.0), ai_item.get('unit') or ''
                cat_name = ai_item.get('category')
                full_note = f"{unit.strip()} {name}".strip() if unit else name
                note_lower = full_note.strip().lower()
                
                m_ing = new_parsed[idx] if idx < len(new_parsed) else {}
                new_food_name = (m_ing.get('food', {}) or {}).get('name', '').strip().lower()
                new_food_id = (m_ing.get('food', {}) or {}).get('id')
                
                # Checkmark Memory Match
                is_checked = False
                if note_lower in checked_notes: is_checked = True
                elif new_food_name and new_food_name in checked_entities: is_checked = True
                else:
                    new_keywords = [w for w in re.findall(r'\w+', note_lower) if len(w) > 3]
                    for kw in new_keywords:
                        if kw in checked_keywords:
                            is_checked = True
                            break

                # Object Matching (to prevent duplicates/re-creation)
                # 1. Direct name match
                match = next((i for i in active_items if i['note'].strip().lower() == note_lower), None)
                # 2. Entity ID match
                if not match and new_food_id:
                    match = next((i for i in active_items if (i.get('foodId') or (i.get('food') or {}).get('id')) == new_food_id), None)
                # 3. Fuzzy core-word match (prevent re-adding slightly differently named items)
                if not match and new_food_name:
                    match = next((i for i in active_items if new_food_name in i['note'].lower()), None)

                if match:
                    matched_ids.add(match['id'])
                    updated = match.copy()
                    updated.update({
                        "note": full_note, 
                        "quantity": qty, 
                        "checked": is_checked, 
                        "labelId": label_name_to_id.get(cat_name) or match.get('labelId')
                    })
                    to_update.append(updated)
                else:
                    to_add.append({
                        "shoppingListId": ACTIVE_LIST_ID, 
                        "note": full_note, 
                        "quantity": qty, 
                        "checked": is_checked, 
                        "labelId": label_name_to_id.get(cat_name), 
                        "position": idx
                    })

            to_delete = [i['id'] for i in active_items if i['id'] not in matched_ids]

            # 6. Apply
            if to_delete: self.client.delete_shopping_list_items_bulk(to_delete)
            if to_update: self.client.update_shopping_list_items_bulk(to_update)
            if to_add: self.client.add_shopping_list_items_bulk(to_add)

            if progress_callback: progress_callback("Sync complete!", 100)
            return True
        except Exception as e:
            print(f"Error during AI shopping list sync: {e}")
            if progress_callback: progress_callback(f"Error: {str(e)}", 100)
            return False

def sync_shopping_list(start_date_str, end_date_str, low_staples_ids=[], progress_callback=None, freezer_items=""):
    from .unified_client import UnifiedMealieClient
    from .gemini_client import GeminiClient
    client, gemini = UnifiedMealieClient(), GeminiClient()
    return ShoppingListSync(client, gemini).sync_shopping_list(start_date_str, end_date_str, low_staples_ids, progress_callback, freezer_items)
