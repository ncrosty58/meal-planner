---
name: shopping-list-sync
description: Generate and synchronize the active shopping list in Mealie.
---

# Mealie Shopping List Synchronization Skill

This skill is responsible for intelligently generating and synchronizing the active shopping list in Mealie based on a weekly meal plan and a list of manually identified low staples. It includes logic for adding recipe ingredients, reconciling with existing staples, and preventing duplicates.

## Inputs
- `active_list_id`: The ID of the active shopping list in Mealie.
- `staples_list_id`: The ID of the staples shopping list in Mealie (for reference and cleaning).
- `meal_plans_json`: A JSON string representing the scheduled meal plans for the week.
- `low_staples_ids`: A list of IDs for staples that are manually marked as low and need to be added to the active list.
- `current_staples_json`: A JSON string representing the current items in the staples shopping list.
- `dirty_dozen_items_json`: A JSON string representing a list of items belonging to the "Dirty Dozen" that should be tagged as "(Buy Organic)".
- `mealie_api_url`: The base URL for the Mealie API.
- `mealie_api_token`: The API token for authenticating with Mealie.

## Workflow

1.  **Initialize:** Start with an empty list of `ingredients_to_add` to the active shopping list and an empty set of `added_items` (lowercase note/name) to track duplicates.

2.  **Process Manually Marked Low Staples:**
    *   Iterate through each `s_id` in `low_staples_ids`.
    *   Find the corresponding staple item from `current_staples_json`.
    *   Clean the staple item's name (remove quantities/units) using the "Mealie Staple Name Cleaning Skill" or similar logic.
    *   If the cleaned name is not already in `added_items`:
        *   Apply "(Buy Organic)" tag if the item is in `dirty_dozen_items`.
        *   Add the item to `ingredients_to_add` with `shoppingListId = active_list_id`, `quantity = 0.0` (for clean display), and `checked = False`.
        *   Add the cleaned name (lowercase) to `added_items`.

3.  **Process Recipe Ingredients from Meal Plan:**
    *   Parse `meal_plans_json` into a list of meal plan entries.
    *   For each dinner entry in `meal_plans_json` that has a `recipeId`:
        *   Fetch full recipe details using the Mealie API. *Note: You will need to make an HTTP GET request to `{mealie_api_url}/api/recipes/{recipeId}` with `mealie_api_token` in headers. You should cache these results if possible to avoid redundant fetches.*
        *   Iterate through each ingredient in the recipe.
        *   For each ingredient, check if it matches any item in `current_staples_json` (using cleaned names for comparison).
        *   **If it's a staple:**
            *   If it's also in `low_staples_ids` (meaning it's a low staple): Add its cleaned name (tagged organic if applicable) to `ingredients_to_add` (if not already added).
            *   If it's *not* in `low_staples_ids`: Skip it (assume sufficient stock).
        *   **If it's NOT a staple:** Add its original name (tagged organic if applicable) to `ingredients_to_add` (if not already added). Set `quantity = 0.0` to prevent Mealie from prepending numerical quantity.

4.  **Clear and Add to Active Shopping List:**
    *   Clear all existing items from the `active_list_id` using the Mealie API (`DELETE` request to `{mealie_api_url}/api/households/shopping/items` with `ids` parameter and `mealie_api_token` in headers).
    *   Add all `ingredients_to_add` items to the `active_list_id` in bulk using the Mealie API (`POST` request to `{mealie_api_url}/api/households/shopping/items/create-bulk` with `mealie_api_token` in headers).

5.  **Error Handling:** Log any errors during API calls or processing steps.

## Output
Return a JSON object with a single key `success` set to `true` if synchronization completes without critical errors, and `false` otherwise. Also include a `message` string summarizings the outcome and `items_added_count`.

## Example Output
```json
{
  "success": true,
  "message": "Successfully synced 25 items to active shopping list.",
  "items_added_count": 25
}
```