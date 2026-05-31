import os
import sys
# Add the project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import timedelta
from mealie_planner.mealie_client import MealieClient
from mealie_planner.utils import get_active_week_range
from mealie_planner import config

def wipe_mealie_data():
    """Wipe meal plans for current and next week and clear the active shopping list."""
    client = MealieClient()
    
    # 1. Calculate planning ranges
    current_start, current_end = get_active_week_range()
    next_start = current_start + timedelta(days=7)
    next_end = current_end + timedelta(days=7)
    
    current_start_str = current_start.strftime("%Y-%m-%d")
    current_end_str = current_end.strftime("%Y-%m-%d")
    next_start_str = next_start.strftime("%Y-%m-%d")
    next_end_str = next_end.strftime("%Y-%m-%d")

    # Clear current week's meal plan
    print(f"Clearing meal plan for current week: {current_start_str} to {current_end_str}")
    existing_plans_current_week = client.get_meal_plan(current_start_str, current_end_str)
    if existing_plans_current_week:
        for p in existing_plans_current_week:
            print(f"Deleting meal plan entry: {p.get('title', p.get('entryType'))} on {p['date']}")
            client.delete_meal_plan_entry(p['id'])
    print(f"Cleared {len(existing_plans_current_week)} entries for current week.")

    # Clear next week's meal plan
    print(f"Clearing meal plan for next week: {next_start_str} to {next_end_str}")
    existing_plans_next_week = client.get_meal_plan(next_start_str, next_end_str)
    if existing_plans_next_week:
        for p in existing_plans_next_week:
            print(f"Deleting meal plan entry: {p.get('title', p.get('entryType'))} on {p['date']}")
            client.delete_meal_plan_entry(p['id'])
    print(f"Cleared {len(existing_plans_next_week)} entries for next week.")

    # Clear active shopping list
    print(f"Clearing active shopping list (ID: {config.ACTIVE_LIST_ID})")
    client.clear_shopping_list(config.ACTIVE_LIST_ID)
    print("Active shopping list cleared.")

    print("Mealie meal plans and active shopping list wiped successfully.")

if __name__ == "__main__":
    wipe_mealie_data()
