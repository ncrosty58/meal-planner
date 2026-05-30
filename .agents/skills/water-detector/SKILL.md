---
name: water-detector
description: Detect whether a grocery or recipe ingredient is plain tap water (which should not be added to a shopping list) vs a specialty water that must be purchased.
---

# Plain Water Detection Skill

This skill classifies ingredient name strings to determine if they represent plain tap water (e.g. water, cold water, tap water) which does not need to be purchased from a store, versus specialty water (e.g. coconut water, rose water) or other ingredients.

## Inputs
- `ingredients_json`: A JSON string representing an array of ingredient names (e.g., `["cold water", "rose water", "filtered water", "coconut water", "water (hot)"]`).

## Workflow

1.  **Parse Input:** Parse `ingredients_json` into a list of individual ingredient strings.

2.  **Classify Each Item:** For each ingredient, determine if it represents *plain water* (which is freely available from a tap/sink and should be excluded from a shopping list) or not.
    *   **Classify as Plain Water (`true`):**
        *   Standard plain water (e.g., "water", "tap water").
        *   Water with basic temperature or physical state qualifiers (e.g., "cold water", "hot water", "warm water", "ice water", "boiling water").
        *   Water with basic filtration qualifiers (e.g., "filtered water", "purified water", "clean water").
        *   Qualifiers inside parentheses or after commas (e.g., "water (cold)", "water, warm").
        *   Phrases describing water for cooking use (e.g., "water for boiling pasta", "water to cover").
    *   **Classify as Non-Plain Water (`false`):**
        *   Specialty or flavored waters that must be purchased (e.g., "coconut water", "rose water", "orange blossom water", "maple water", "birch water").
        *   Carbonated or mineral waters (e.g., "sparkling water", "soda water", "carbonated water", "mineral water", "tonic water").
        *   Distilled water (often purchased for specific recipes or appliances).
        *   Salt water, sea water.
        *   Any other ingredient that contains the letters "water" but is not liquid water (e.g., "water chestnuts", "watermelon").
        *   Any non-water ingredient.

3.  **Construct Output:** Return a JSON object where:
    *   Each key is one of the *original* raw ingredient strings from the input array.
    *   Each value is a boolean: `true` if the item is plain water, and `false` otherwise.
    *   Do not include any additional text or explanation in the output.

## Example Input
```json
["2 cups cold water", "rose water", "1 liter sparkling water", "water", "water chestnuts", "distilled water", "warm water (for yeast)"]
```

## Example Output
```json
{
  "2 cups cold water": true,
  "rose water": false,
  "1 liter sparkling water": false,
  "water": true,
  "water chestnuts": false,
  "distilled water": false,
  "warm water (for yeast)": true
}
```
