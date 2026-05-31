---
name: recipe-nutrition-imputation
description: Estimate structured per-serving nutritional information for recipes missing this data.
---

# Recipe Nutrition Imputation Skill

This skill provides instructions for generating structured per-serving nutritional estimates for Mealie recipes that lack complete nutritional profiles.

## Inputs
- `name`: The name of the recipe.
- `description`: A description of the dish.
- `servings`: The number of servings/yield of the recipe.
- `ingredients`: The raw or structured ingredients list.
- `instructions`: The step-by-step preparation and cooking instructions.

## Workflow

1.  **Analyze Portions & Servings**: Use the `servings` count (fallback to 4 if not specified) to calculate the nutritional values per single serving of the prepared dish.
2.  **Estimate Macro/Micro Nutrients**: Based on the quantities and types of ingredients, estimate the following nutritional values per serving:
    *   `calories`: Total energy (kcal, integer).
    *   `proteinContent`: Protein (g, decimal or integer).
    *   `carbohydrateContent`: Total carbohydrates (g, decimal or integer).
    *   `fatContent`: Total fat (g, decimal or integer).
    *   `fiberContent`: Dietary fiber (g, decimal or integer). Highly prioritize fiber-rich foods (beans, vegetables, whole grains).
    *   `sodiumContent`: Sodium (mg, integer). Consider salt, soy sauce, stocks, etc.
    *   `sugarContent`: Sugar (g, decimal or integer).
    *   `cholesterolContent`: Cholesterol (mg, integer).
3.  **Ensure Nutritional Consistency**:
    *   Total calories should align with the estimated fat (9 kcal/g), carbohydrates (4 kcal/g), and protein (4 kcal/g).
    *   Use realistic ingredient yields (e.g. green lentils are high in fiber and protein; olive oil adds fat; green leafy vegetables add small amounts of fiber/carbs).
4.  **Response Format**:
    *   Respond strictly in a single JSON object.
    *   All values must be formatted as strings representing numbers (Mealie schema requirement).

## Example Response Format
```json
{
  "calories": "350",
  "proteinContent": "23",
  "carbohydrateContent": "48",
  "fatContent": "9",
  "fiberContent": "20",
  "sodiumContent": "650",
  "sugarContent": "5",
  "cholesterolContent": "0"
}
```
