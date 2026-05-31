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
            # 1. Fetch current state
            staples = self.client.get_shopping_list_items(STAPLES_LIST_ID)
            active_items = self.client.get_shopping_list_items_for_list(ACTIVE_LIST_ID)
            
            low_ids_clean = {s_id.replace('-', '').lower() for s_id in low_staples_ids}
            
            # Identify which items on the active list are "staples"
            # We match by name against the master staples list
            staple_names = {s['note'].strip().lower(): s for s in staples}
            
            active_staple_notes = []
            active_non_staple_notes = []
            for item in active_items:
                note = item['note'].strip().lower()
                if note in staple_names:
                    active_staple_notes.append(item)
                else:
                    active_non_staple_notes.append(item)

            # 2. Determine Additions
            # Items in low_ids_clean that aren't on the active list yet
            to_add = []
            active_notes_set = {i['note'].strip().lower() for i in active_items}
            
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

            # 3. Determine Deletions
            # Items on the active list that ARE staples but are NOT in low_ids_clean anymore
            to_delete_ids = []
            for item in active_staple_notes:
                # Find the master staple this item belongs to
                master_staple = staple_names.get(item['note'].strip().lower())
                if master_staple:
                    m_id = master_staple['id'].replace('-', '').lower()
                    if m_id not in low_ids_clean:
                        to_delete_ids.append(item['id'])

            # 4. Execute updates
            if to_delete_ids:
                print(f"[Sync] Removing {len(to_delete_ids)} staples no longer marked as low.")
                self.client.delete_shopping_list_items_bulk(to_delete_ids)
            
            if to_add:
                print(f"[Sync] Adding {len(to_add)} new low staples.")
                self.client.add_shopping_list_items_bulk(to_add)

            return True
        except Exception as e:
            print(f"Error during fast staples sync: {e}")
            return False

    def sync_shopping_list(self, start_date_str, end_date_str, low_staples_ids=[], progress_callback=None, freezer_items="") -> bool:
        """Sync active shopping list based on scheduled recipes and low staples using the unified shopping-list-sync AI skill."""
        print(f"Starting AI shopping list sync for {start_date_str} to {end_date_str}...")
        if progress_callback:
            progress_callback("AI shopping list sync started...", 90)
        try:
            # Give Mealie a moment to process previous scheduling calls
            time.sleep(1.0)

            # 1. Fetch data from Mealie
            meal_plans = self.client.get_meal_plan(start_date_str, end_date_str)
            print(f"[Sync] Found {len(meal_plans)} total meal plan entries for period.")
            
            staples = self.client.get_shopping_list_items(STAPLES_LIST_ID)
            
            # Build set of low staples IDs (hyphen-insensitive)
            low_ids_clean = {s_id.replace('-', '').lower() for s_id in low_staples_ids}
            
            # Map low staples to their notes (names) and build staples notes list
            staples_notes = [item['note'] for item in staples]
            staple_names_lower = {s['note'].strip().lower() for s in staples}

            # State Preservation: If a staple is CURRENTLY on the active list, 
            # treat it as "low" so the AI doesn't filter it out during this sync.
            active_items = self.client.get_shopping_list_items_for_list(ACTIVE_LIST_ID)
            active_staple_names = []
            for item in active_items:
                note = item.get('note', '').strip().lower()
                if note in staple_names_lower:
                    active_staple_names.append(item['note'])

            # Parse freezer items
            inventory_items = []
            if freezer_items:
                inventory_items = [i.strip() for i in freezer_items.split(",") if i.strip()]

            low_staples_notes = []
            for item in staples:
                clean_id = item['id'].replace('-', '').lower()
                if clean_id in low_ids_clean:
                    low_staples_notes.append(item['note'])
            
            # Combine modal-marked low staples with currently active ones
            combined_low_staples = list(set(low_staples_notes + active_staple_names))
            
            # 3. Fetch current list state to build a Checkmark Memory
            if progress_callback:
                progress_callback("Reading your current shopping progress...", 95)
            
            try:
                active_items = self.client.get_shopping_list_items_for_list(ACTIVE_LIST_ID)
            except Exception as e:
                print(f"[Sync] Error fetching current items: {e}")
                active_items = []

            # Match items by "Base Food Name" (Stable Fingerprint)
            # We parse the CURRENT list items to see what they actually are
            current_checkmark_map = {} # Maps base_food_name -> checked_status
            active_staple_names = []
            
            if active_items:
                current_notes = [item.get('note', '') for item in active_items]
                current_parsed = self.client.parse_raw_ingredients(current_notes)
                
                for idx, item in enumerate(active_items):
                    p_ing = current_parsed[idx] if idx < len(current_parsed) else {}
                    food_name = (p_ing.get('food', {}) or {}).get('name', '').strip().lower()
                    
                    if food_name:
                        if item.get('checked'):
                            current_checkmark_map[food_name] = True
                        
                        # Identify if this active item is a staple for AI protection
                        if food_name in staple_names_lower:
                            active_staple_names.append(item['note'])

            # 4. Call the unified shopping-list-sync AI skill
            if progress_callback:
                progress_callback("Generating optimized shopping list...", 96)
            
            # Fetch standardized labels from Mealie
            all_labels = self.client.get_labels()
            available_label_names = [label['name'] for label in all_labels]
            label_name_to_id = {label['name']: label['id'] for label in all_labels}

            # Combine modal-marked low staples with currently active ones to ensure they don't disappear
            combined_low_staples = list(set(low_staples_notes + active_staple_names))

            payload = {
                "ingredients": raw_recipe_ingredients,
                "staples": staples_notes,
                "inventory_items": inventory_items,
                "low_staples": combined_low_staples,
                "available_labels": available_label_names
            }
            
            prompt = (
                """You are an expert in the 'Shopping List Sync Skill'.

""" +
                _SHOPPING_LIST_SYNC_SKILL_DEFINITION + """

### CONTEXT FOR THIS INVOCATION:
""" +
                f"Input Data: {json.dumps(payload)}\n" +
                f"Family Dietary Rules: {FAMILY_DIETARY_RULES_PROMPT}\n\n" +
                "Return ONLY the JSON array of objects as specified in the skill definition."
            )
            
            print(f"--- AI SHOPPING LIST SYNC PROMPT ({len(raw_recipe_ingredients)} ingredients, {len(combined_low_staples)} staples) ---")
            ai_response = self.gemini.call(prompt, expect_json=True)
            
            try:
                final_items = json.loads(ai_response)
                if not isinstance(final_items, list):
                    raise SkillParsingError("AI did not return a list for shopping list sync")
            except Exception as e:
                raise SkillParsingError(f"Failed to parse AI response: {e}")

            # 5. High-Fidelity Safe Merge
            if progress_callback:
                progress_callback("Merging updates and locking checkmarks...", 98)

            # Step A: Identify what the NEW items are
            new_item_names = [item.get('name', 'Unknown') for item in final_items]
            new_item_structures = self.client.parse_raw_ingredients(new_item_names)
            
            # Step B: Match against Checkmark Memory
            to_add = []
            to_update = []
            matched_current_ids = set()
            
            # Build current item lookup by ID and note
            current_id_map = {item['id']: item for item in active_items}
            current_note_map = {item['note'].strip().lower(): item for item in active_items}

            for idx, ai_item in enumerate(final_items):
                name = ai_item.get('name', 'Unknown Item')
                qty = ai_item.get('quantity', 1.0)
                unit = ai_item.get('unit') or ''
                category_name = ai_item.get('category')
                
                label_id = label_name_to_id.get(category_name)
                full_note = f"{unit.strip()} {name}".strip() if unit else name
                
                # Get base food name for the NEW item
                m_ing = new_item_structures[idx] if idx < len(new_item_structures) else {}
                new_food_name = (m_ing.get('food', {}) or {}).get('name', '').strip().lower()
                
                # Try to find match in current list
                match = current_note_map.get(full_note.strip().lower())
                
                # If no direct note match, match by Food Entity
                if not match and new_food_name:
                    # Look through active items to find one with the same base food
                    for item in active_items:
                        # We already parsed these in step 3
                        pass # Placeholder for logic below
                
                # Optimized Matching Loop
                is_checked = False
                if match:
                    is_checked = match.get('checked', False)
                    matched_current_ids.add(match['id'])
                elif new_food_name and new_food_name in current_checkmark_map:
                    is_checked = True
                    # Find the specific item ID to mark it as matched
                    for item in active_items:
                        # Re-derive food name for match
                        # (Ideally we'd cache this in Step 3)
                        pass
                
                # If we found a base-name match, find the item to mark it as matched
                # This prevents it from being deleted
                if not match:
                    for item in active_items:
                        if item['id'] in matched_current_ids: continue
                        # Use a simple contains check if we don't have full structure
                        if new_food_name and new_food_name in item['note'].lower():
                            match = item
                            matched_current_ids.add(item['id'])
                            break

                if match:
                    updated_item = match.copy()
                    updated_item['note'] = full_note
                    updated_item['quantity'] = qty
                    updated_item['checked'] = is_checked
                    updated_item['labelId'] = label_id or match.get('labelId')
                    to_update.append(updated_item)
                else:
                    to_add.append({
                        "shoppingListId": ACTIVE_LIST_ID,
                        "note": full_note,
                        "quantity": qty,
                        "checked": False,
                        "labelId": label_id,
                        "position": idx
                    })

            # Step C: Cleanup
            to_delete_ids = [item['id'] for item in active_items if item['id'] not in matched_current_ids]

            # 6. Execute in Mealie
            if progress_callback:
                progress_callback("Writing changes to Mealie...", 99)

            if to_delete_ids:
                print(f"[Sync] Deleting {len(to_delete_ids)} old items.")
                self.client.delete_shopping_list_items_bulk(to_delete_ids)
            
            if to_update:
                print(f"[Sync] Updating {len(to_update)} existing items.")
                self.client.update_shopping_list_items_bulk(to_update)
                
            if to_add:
                print(f"[Sync] Adding {len(to_add)} new items.")
                self.client.add_shopping_list_items_bulk(to_add)

            if progress_callback:
                progress_callback("Shopping list sync complete!", 100)
            return True
            
        except Exception as e:
            print(f"Error during AI shopping list sync: {e}")
            if progress_callback:
                progress_callback(f"Error during shopping list sync: {str(e)}", 100)
            return False

def sync_shopping_list(start_date_str, end_date_str, low_staples_ids=[], progress_callback=None, freezer_items=""):
    """Standalone helper to run sync with fresh clients."""
    from .unified_client import UnifiedMealieClient
    from .gemini_client import GeminiClient
    client = UnifiedMealieClient()
    gemini = GeminiClient()
    syncer = ShoppingListSync(client, gemini)
    return syncer.sync_shopping_list(start_date_str, end_date_str, low_staples_ids, progress_callback, freezer_items)
