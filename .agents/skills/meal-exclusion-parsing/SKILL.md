---
name: meal-exclusion-parsing
description: Parse free-text meal exclusions into structured JSON.
---

# Mealie Meal Exclusion Parsing Skill

This skill provides instructions for interpreting a free-text description of meals to skip or opt out of for a given week, and returning a structured JSON object.

## Inputs
- `user_input`: A free-text string describing which meals to skip or opt out of.
- `week_dates_context`: A string describing the upcoming week's dates (e.g., "Monday (2026-06-02), Tuesday (2026-06-03), ..."). This is for context only.

## Workflow

1.  **Parse User Input:** Read the `user_input` to identify which meals on which days should be skipped.

2.  **Identify Valid Days and Meals:**
    *   Valid day names are: `Monday`, `Tuesday`, `Wednesday`, `Thursday`, `Friday`, `Saturday`, `Sunday`.
    *   Valid meal names are: `breakfast`, `lunch`, `dinner`.

3.  **Construct Output:** Return a JSON object where:
    *   Keys are valid day names (e.g., `"Monday"`).
    *   Values are arrays of valid meal names to SKIP for that day (e.g., `["dinner"]`).
    *   Only include days where at least one meal should be skipped.
    *   If no meals should be skipped, return an empty object `{}`.
    *   Do not include any additional text or explanation beyond the JSON.

## Example Input (user_input)
`"skip dinner Saturday and Sunday"`

## Example Context (week_dates_context)
`"The week runs: Monday (2026-06-02), Tuesday (2026-06-03), Wednesday (2026-06-04), Thursday (2026-06-05), Friday (2026-06-06), Saturday (2026-06-07), Sunday (2026-06-08)."`

## Example Output
```json
{
  "Saturday": ["dinner"],
  "Sunday": ["dinner"]
}
```