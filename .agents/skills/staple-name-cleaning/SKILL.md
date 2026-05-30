---
name: staple-name-cleaning
description: Clean grocery item names by removing quantities and units.
---

# Mealie Staple Name Cleaning Skill

This skill provides instructions for cleaning grocery item strings by removing quantities, numbers, fractions, and units of measure, and then formatting the cleaned name to be Title Cased.

## Inputs
- `items_json`: A JSON string representing an array of raw grocery item strings.

## Workflow

1.  **Parse Input:** The input `items_json` will be a JSON array of strings (e.g., `["6 tbsp butter", "1 gallon milk", "2 cloves garlic"]`). Parse this into a list of individual strings.

2.  **Clean Each Item:** For each item string in the list:
    *   Remove any leading or embedded quantities, numbers, fractions, or units of measure (e.g., "6 tbsp", "1 gallon", "2 cloves", "10 oz", "1/2 cup").
    *   Trim any leading or trailing whitespace.
    *   Format the resulting clean name to be Title Cased (e.g., "butter", "milk", "garlic").

3.  **Construct Output:** Return a JSON object where:
    *   Each key is one of the *original* raw grocery item strings from the input.
    *   Each value is its corresponding *cleaned and Title Cased* name.
    *   Do not include any additional text or explanation in the output.

## Example Input
```json
["2 lbs chicken breast", "1/2 cup sugar", "3 large eggs"]
```

## Example Output
```json
{
  "2 lbs chicken breast": "Chicken Breast",
  "1/2 cup sugar": "Sugar",
  "3 large eggs": "Eggs"
}
```
