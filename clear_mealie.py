import os
import sys
# Add the project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from datetime import datetime, timedelta
import pytz

import meal_planner
import config

def get_current_and_next_planning_dates():
    today = datetime.now(pytz.timezone(config.TIMEZONE))

    # Calculate current planning week (Saturday to Friday)
    # If today is Saturday or Sunday, this will be the current week
    # If today is Monday-Friday, this will be the *past* Saturday to upcoming Friday
    days_since_saturday = (today.weekday() - 5 + 7) % 7
    current_week_start = today - timedelta(days=days_since_saturday)
    current_week_end = current_week_start + timedelta(days=6)

    # Calculate next planning week (Saturday to Friday)
    next_week_start = current_week_end + timedelta(days=1)
    next_week_end = next_week_start + timedelta(days=6)

    return (
        current_week_start.strftime("%Y-%m-%d"), current_week_end.strftime("%Y-%m-%d"),
        next_week_start.strftime("%Y-%m-%d"), next_week_end.strftime("%Y-%m-%d")
    )

def wipe_mealie_data():
    print("Attempting to wipe Mealie meal plans and active shopping list...")
    client = meal_planner.MealieClient()

    current_start_str, current_end_str, next_start_str, next_end_str = get_current_and_next_planning_dates()

    # Clear current week's meal plan
    print(f"Clearing meal plan for current week: {current_start_str} to {current_end_str}")
    existing_plans_current_week = client.get_meal_plan(current_start_str, current_end_str)
    for p in existing_plans_current_week:
        print(f"Deleting meal plan entry: {p.get('title', p.get('entryType'))} on {p['date']}")
        client.delete_meal_plan_entry(p['id'])
    print(f"Cleared {len(existing_plans_current_week)} entries for current week.")

    # Clear next week's meal plan
    print(f"Clearing meal plan for next week: {next_start_str} to {next_end_str}")
    existing_plans_next_week = client.get_meal_plan(next_start_str, next_end_str)
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