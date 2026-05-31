---
name: weekly-meal-selection
description: Generate a complete 7-day meal plan (Breakfast, Lunch, Dinner) based on family preferences, perishability rules, and intelligent lunch selection.
---

# Mealie Weekly Meal Selection Skill

This skill is responsible for generating a complete 7-day meal plan. It intelligently selects dinner recipes from a provided catalogue, assigns breakfasts, and strategically chooses lunches based on the previous night's dinner and nutritional balance.

## Inputs
- `family_dietary_rules_prompt`: Family-specific dietary rules and preferences.
- `start_date`: The first day of the plan (always a Saturday).
- `exclusions`: A JSON object mapping day names to lists of meals to skip (e.g., `{"Monday": ["dinner"]}`).
- `freezer_pantry_fridge_items_priority`: Items to use up this week.
- `special_requests`: Theme or specific request text.
- `recently_planned_recipes`: List of recipe names to avoid repeating.
- `recipe_catalogue_json`: Available Mealie dinner recipes.

## Workflow

1.  **Plan Dinners (Selection):** Select exactly the required number of dinner recipes from the catalogue (one for each non-excluded night).
    *   **Anti-Hallucination:** ONLY select IDs from the provided catalogue.
    *   **Priorities:** High: "Use up" items; Medium: Special requests; General: Variety, fiber, no processed meats.

2.  **Plan Dinners (Ordering):** 
    *   **Perishability:** Fresh/perishable ingredients go Early Week (Sat-Tue). Frozen/shelf-stable go Late Week (Wed-Fri).
    *   **"Use Up" Items:** If they are frozen/stable, they MUST go Late Week.

3.  **Plan Lunches (Intelligent Selection):** For each day, choose between **"Leftovers"** or **"PB&J Sandwich"**.
    *   **Leftovers Rule:** Assign "Leftovers" for lunch if the PREVIOUS night's dinner was a large, home-cooked meal suitable for leftovers.
    *   **PB&J Rule:** Assign "PB&J Sandwich" if:
        1. The previous night's dinner was "Eating Out" (no leftovers available).
        2. The previous night's dinner was a smaller or lighter meal.
        3. To provide variety after several consecutive days of leftovers.
    *   **Nutritional Balance:** If the upcoming dinner is very heavy, lean toward a lighter lunch.

4.  **Plan Breakfasts:** Assign standard options (Cereal & Milk, Yogurt with Granola, etc.) providing daily variety.

## Output
Return a JSON object containing a `days` array. Each day must have `date`, and a `meals` object with `breakfast`, `lunch`, and `dinner`. 
For `dinner`, use the `id` from the catalogue. For `breakfast` and `lunch`, use the string title (e.g., "Leftovers", "PB&J Sandwich", "Cereal & Milk").

## Example Output
```json
{
  "days": [
    {
      "date": "2026-05-30",
      "meals": {
        "breakfast": "Cereal & Milk",
        "lunch": "Leftovers",
        "dinner": "recipe-uuid-123"
      }
    },
    ...
  ]
}
```