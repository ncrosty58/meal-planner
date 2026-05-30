---
name: recipe-finder
description: Search for recipes on the web and import them into Mealie.
---

# Mealie Recipe Finder Skill

This skill provides instructions for intelligently searching the web for recipes and importing them into a Mealie instance, focusing on identifying single, complete recipes and avoiding recipe collections or irrelevant articles.

## Inputs
- `ingredient`: The primary ingredient for which to find a recipe.
- `mealie_api_url`: The base URL for the Mealie API.
- `mealie_api_token`: The API token for authenticating with Mealie.
- `user_agent`: A User-Agent string for web requests.
- `existing_recipe_ids`: A list of recipe IDs already present in Mealie to avoid re-importing.

## Workflow

1.  **Construct Search Query:**
    *   Determine if the `ingredient` contains common meat keywords (e.g., 'chicken', 'beef', 'salmon').
    *   If yes, form the query: `"healthy recipe with {ingredient}"`.
    *   If no (implying vegetarian), form the query: `"healthy vegetarian recipe with {ingredient}"`.

2.  **Perform Web Search (DuckDuckGo):**
    *   Encode the search query for a DuckDuckGo HTML search (`https://html.duckduckgo.com/html/`).
    *   Make an HTTP GET request to DuckDuckGo using `urllib.request` and the provided `user_agent`.
    *   Parse the HTML response using BeautifulSoup.

3.  **Extract and Filter Potential Recipe Links:**
    *   Find all `<a>` tags with `href` attributes in the parsed HTML.
    *   **Unwrap DuckDuckGo proxied links:** If a link contains `uddg=`, extract the actual URL from the `uddg` query parameter.
    *   **Exclude search engine links:** Filter out links from `duckduckgo.com` or `yandex.com`.
    *   **Keyword filter:** Only consider links that contain common recipe-related keywords in their lowercase URL (e.g., 'recipe', 'food', 'cook', 'kitchen', 'eat').
    *   Collect up to the first 5 unique potential recipe links.

4.  **Recipe Link Filtering and AI-Driven Validation:**
    *   For each potential recipe link:
        *   Make an HTTP GET request to the link to fetch its HTML content (with a short timeout, e.g., 5 seconds).
        *   Parse the HTML using BeautifulSoup to extract the `<title>` tag's text and the `content` of the `<meta name="description">` tag.
        *   **Programmatic Listicle Pre-filter**: Inspect the title and meta description. Reject the link programmatically without calling the AI if it is flagged as a listicle or collection. Flag listicles using:
            *   Regex matches for a number followed by recipe words in the title, e.g. `\b\d+\s*\+?\s*(?:best|delicious|easy|healthy|quick|favorite|great|ideas|recipes|meals|dinners)\b`.
            *   Presence of keywords like `'roundup'`, `'round-up'`, `'listicles'`, `'collection of'`, `'best recipes'`, or `'favorite recipes'`.
        *   **AI Validation**: If not programmatically filtered, construct an AI validation prompt:
            ```text
            You are a recipe link validator. Given a URL, page title, and description, determine if the content at the URL is a single, complete recipe.

            CRITICAL RULES:
            1. Ignore recipe collections, lists, roundups, compilations, galleries, directories, or blog posts about cooking (e.g. "21 Delicious Recipes", "15 Chicken Ideas", "Best ways to cook...").
            2. Focus ONLY on pages that contain ONE specific, single recipe with concrete ingredients and instructions for that single dish.
            3. If the title, URL, or description contains listicle keywords or patterns like "X recipes", "X best...", "X+ recipes", "roundup", "collection", "ideas for", respond with 'NO'.
            4. Respond with 'YES' if it is a single specific recipe, and 'NO' if it is a collection or not a recipe page.
            5. Respond with ONLY 'YES' or 'NO'. Do not add any other text, explanation, or punctuation.

            URL: {url}
            Title: {title}
            Description: {description}
            Is this a single recipe?
            ```
        *   Call `call_gemini` with this prompt (expecting plain text response).
        *   If the AI response contains `"YES"`, consider the link validated.

5.  **Import Validated Recipes into Mealie:**
    *   For each validated recipe link (up to 5, or until one is successfully imported):
        *   Construct a Mealie API payload with the URL, setting `includeCategories` and `includeTags` to `True`.
        *   Make an HTTP POST request to `{mealie_api_url}/api/recipes/create/url` with the payload and `mealie_api_token` in headers.
        *   If the import is successful (status code 200 or 201), return `True` (indicating success).

6.  **Error Handling:**
    *   Log any errors during web search, link validation, or Mealie import.
    *   If no recipes are successfully imported after all attempts, return `False`.

## Output
- `True` if a recipe was successfully found and imported.
- `False` if no suitable recipe was found or an error occurred. 
