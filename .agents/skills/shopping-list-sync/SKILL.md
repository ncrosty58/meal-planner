---
name: shopping-list-sync
description: Generate the final active shopping list by filtering out plain water and non-low staples from weekly ingredients, cleaning names, and aggregating quantities.
---

# Shopping List Sync Skill

This skill takes the raw ingredient strings from dinner recipes, a list of household staples, and a list of manually identified low staples, and generates the final structured active shopping list.

## Inputs
- `payload`: A JSON object containing:
    - `ingredients`: A list of raw recipe ingredient strings (e.g. `["2 cloves garlic, minced", "1 lb chicken breast"]`).
    - `staples`: A list of staple names already in the house (e.g. `["salt", "pepper"]`).
    - `inventory_items`: A list of specific items the user wants to "use up" from their freezer/pantry/fridge (e.g. `["1 lb chicken thighs", "pesto sauce"]`).
    - `low_staples`: A list of staple names that are currently running low and MUST be added (e.g. `["garlic"]`).
    - `available_labels`: A list of actual category labels from the user's Mealie instance (e.g. `["1. Produce: Vegetables & Greens", "2. Bakery & Bread"]`).
- `family_dietary_rules`: The family-specific dietary rules and preferences (which includes the "Dirty Dozen" list).

## Workflow

1.  **Exclude Plain Water:**
    - Detect any ingredients representing plain tap water (e.g., "water", "cold water", "hot water", "tap water", "water to cover"). Exclude them entirely from the output.
    - Keep specialty waters that must be purchased (e.g., "coconut water", "rose water", "sparkling water").

2.  **Filter Staples and Inventory (Rigorous Semantic Matching):**
    - You MUST compare every recipe ingredient against the `staples` and `inventory_items` lists.
    - **Deep Semantic Filtering:** Do not just look for exact name matches. Use your culinary knowledge to identify if an ingredient is a form of a staple.
        - *Example:* If "Olive Oil" is a staple, you MUST filter out "Extra Virgin Olive Oil", "2 tbsp Olive Oil", "Olive oil for frying", etc.
        - *Example:* If "Garlic" is a staple, filter out "3 cloves Garlic", "Minced Garlic", etc.
    - **Exception Rule:** If the matched staple is explicitly listed in the `low_staples` list, you MUST include it in the final list.
    - **Inventory Rule:** If an ingredient matches an `inventory_item`, filter it out.
    - **Rule of Thumb:** If Nathan and Kristin already have it (Staple) or want to use it up (Inventory), and it's NOT low (Low Staples), do not put it on the shopping list.

3.  **Clean Ingredient Names & Organic Tagging:**
    - For each ingredient, extract the core name by removing quantities, units, and preparation instructions.
    - **Organic Tagging (Dirty Dozen):** If the cleaned ingredient name matches any item from the "Dirty Dozen" list found in the `family_dietary_rules`, automatically append **(Buy Organic)** to the name.
    - Format and capitalize the resulting ingredient name in Title Case (e.g. "1 lb spinach" -> "Spinach (Buy Organic)", "3 cloves garlic" -> "Garlic").

4.  **Extract Unit and Aggregate Quantities:**
    - For each ingredient, extract the unit of measure (e.g., "lb", "oz", "cup", "can", "clove", "tsp", "tbsp").
    - If the ingredient matches a staple, the `unit` should be `null` (units are not used for staple items).
    - If the same cleaned ingredient name appears multiple times, aggregate their quantities by summing them if the units are compatible.
    - If units are incompatible or missing, default to a sensible aggregate quantity or a default quantity of 1.0.

5.  **Include Manually Added Low Staples:**
    - Ensure any item from `low_staples` that was marked as low is included in the output list with `unit: null`.

6.  **Categorize Using Available Labels (Grocery Store Path Logic):**
    - You must categorize items into exactly one of the provided `available_labels`.
    - **Physical Layout Logic:** Use your knowledge of grocery store layouts to group items. The provided labels are ordered 1-9 to reflect a standard walking path.
    - **Clean Naming:** For the `category` field in the output, you must use the EXACT string from `available_labels`.
    - **Natural Sorting:** Sort the final JSON array first by the category number (1-9), and then alphabetically by ingredient name within each category. This ensures the list is ready for shopping.

7.  **Construct Output:**
    - Return a JSON array of objects.
    - Each object:
      - `name`: Cleaned, Title Cased name (e.g. "Chicken Breast").
      - `quantity`: Aggregated numeric quantity as a float (e.g. 1.0 or 2.0).
      - `unit`: The extracted unit of measure (e.g. "lb", "cup", "can"). For staples, this MUST be `null`.
      - `category`: The EXACT zone name from `available_labels` (e.g. "1. Produce: Vegetables & Greens").
    - Do not include any extra text or conversational response.

## Example Input
```json
{
  "ingredients": ["2 lbs chicken breast", "1/2 cup salt", "3 cloves garlic", "2 cups water", "1 can coconut water", "1/2 tsp fresh ginger"],
  "staples": ["salt", "pepper", "garlic", "olive oil"],
  "low_staples": ["garlic"],
  "available_labels": ["1. Produce: Vegetables & Greens", "3. Meat, Poultry & Seafood", "4. Dairy & Eggs", "7. Beverages"]
}
```

## Example Output
```json
[
  {
    "name": "Fresh Ginger",
    "quantity": 0.5,
    "unit": "tsp",
    "category": "1. Produce: Vegetables & Greens"
  },
  {
    "name": "Garlic",
    "quantity": 3.0,
    "unit": null,
    "category": "1. Produce: Vegetables & Greens"
  },
  {
    "name": "Chicken Breast",
    "quantity": 2.0,
    "unit": "lbs",
    "category": "3. Meat, Poultry & Seafood"
  },
  {
    "name": "Coconut Water",
    "quantity": 1.0,
    "unit": "can",
    "category": "7. Beverages"
  }
]
```