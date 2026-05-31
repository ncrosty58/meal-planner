---
name: recipe-finder
description: Validate if a URL, title, and description represent a single, complete recipe with an image.
---

# Mealie Recipe Link Validator Skill

This skill provides instructions for determining if a potential web link is a high-quality, single, complete recipe suitable for import into Mealie.

## Inputs
- `url`: The URL of the potential recipe page.
- `title`: The `<title>` of the page.
- `description`: The meta description or a short snippet of the page content.

## Workflow

1.  **Identify Single Recipes:**
    *   The page must contain exactly ONE specific recipe.
    *   It must have concrete ingredients and instructions for that single dish.
    *   **Respond with 'YES'** only if it is a single recipe.

2.  **Filter Out Listicles and Collections:**
    *   **Respond with 'NO'** if the content is a collection, list, roundup, compilation, gallery, or directory (e.g., "21 Delicious Recipes", "15 Chicken Ideas", "Best ways to cook...").
    *   Reject patterns like "X recipes", "X best...", "X+ recipes", "roundup", "collection", "ideas for".

3.  **Visual Quality Constraint:**
    *   Assume recipes without a featured image are invalid for this application. If the title or description suggests a low-quality or text-only blog post without a clear photo, **respond with 'NO'**. (Note: The calling application will perform the final visual validation after import).

4.  **Response Format:**
    *   Respond with ONLY 'YES' or 'NO'. 
    *   Do not add any other text, explanation, or punctuation.

## Example Input
```text
URL: https://example.com/best-chicken-curry
Title: Easy 30-Minute Chicken Curry Recipe
Description: This single-pot chicken curry is packed with flavor and perfect for a quick weeknight dinner.
```

## Example Output
`YES`
