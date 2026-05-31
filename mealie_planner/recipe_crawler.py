import re
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
import requests

from .config import load_skill_md, _RECIPE_FINDER_SKILL_DEFINITION

class RecipeCrawler:
    def __init__(self, mealie_client, gemini_client):
        self.client = mealie_client
        self.gemini = gemini_client

    def find_recipe_for_ingredient(self, ingredient, all_recipes=None):
        """Look for a recipe in Mealie containing the ingredient in its name or ingredients notes."""
        if all_recipes is None:
            all_recipes = self.get_recipes_from_db()
        
        ing_lower = ingredient.lower()
        
        # 1. Match recipe name (handle Mealie duplicate suffixes like ' (1)')
        for r in all_recipes:
            name = r['name']
            cleaned_name = re.sub(r'\s*\(\d+\)$', '', name).lower()
            if ing_lower in cleaned_name:
                return r['id']
                
        # 2. Check recipe ingredients
        for r in all_recipes:
            for ing_text in r.get('ingredients', []):
                if ing_lower in ing_text.lower():
                    return r['id']            
        return None

    def find_and_import_recipe(self, ingredient, existing_recipe_ids=[]) -> bool:
        """Search for and import a recipe into Mealie using the Mealie Recipe Finder Skill workflow."""
        print(f"No existing recipe using '{ingredient}'. Starting Recipe Finder workflow...")
        
        # Pre-fetch all recipes to check for existing orgURLs and prevent duplicates
        all_recipes_overview = self.client.get_all_recipes()
        existing_urls = {r.get('orgURL') for r in all_recipes_overview if r.get('orgURL')}

        # 1. Construct Search Query
        meat_keywords = {'chicken', 'beef', 'salmon', 'turkey', 'pork', 'fish', 'steak', 'tuna', 'poultry', 'lamb'}
        ingredient_lower = ingredient.lower()
        has_meat = any(kw in ingredient_lower for kw in meat_keywords)
        if has_meat:
            query = f"healthy recipe with {ingredient}"
        else:
            query = f"healthy vegetarian recipe with {ingredient}"
            
        print(f"[Recipe Finder] Query: {query}")
        
        # 2. Perform Web Search (DuckDuckGo)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        
        try:
            req = urllib.request.Request(search_url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read()
        except Exception as e:
            print(f"[Recipe Finder] DuckDuckGo search request failed: {e}")
            return False
            
        soup = BeautifulSoup(html, 'html.parser')
        
        # 3. Extract and Filter Potential Recipe Links
        potential_links = []
        recipe_keywords = {'recipe', 'food', 'cook', 'kitchen', 'eat'}
        
        for a in soup.find_all('a', href=True):
            href = a['href']
            
            # Unwrap DuckDuckGo proxied links
            if 'uddg=' in href:
                parsed_href = urllib.parse.urlparse(href)
                query_params = urllib.parse.parse_qs(parsed_href.query)
                if 'uddg' in query_params:
                    href = query_params['uddg'][0]
                    
            # Filter search engine links
            parsed_url = urllib.parse.urlparse(href)
            domain = parsed_url.netloc.lower()
            if 'duckduckgo' in domain or 'yandex' in domain or 'google' in domain or 'bing' in domain:
                continue
                
            # Keyword filter
            href_lower = href.lower()
            if any(kw in href_lower for kw in recipe_keywords):
                if href not in potential_links:
                    potential_links.append(href)
                    if len(potential_links) >= 5:
                        break
                        
        print(f"[Recipe Finder] Found {len(potential_links)} potential links for validation.")
        
        # Import RecipeNutrition locally to avoid circular dependencies
        from .recipe_nutrition import RecipeNutrition
        nutrition_imputer = RecipeNutrition(self.client, self.gemini)

        # 4. AI-Driven Recipe Link Validation & 5. Import Validated Recipes
        for url in potential_links:
            print(f"[Recipe Finder] Fetching page for validation: {url}")
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=5) as response:
                    page_html = response.read()
            except Exception as e:
                print(f"[Recipe Finder] Failed to fetch {url}: {e}")
                continue
                
            page_soup = BeautifulSoup(page_html, 'html.parser')
            
            # Extract title and description
            title = page_soup.title.string.strip() if page_soup.title else ""
            desc_meta = page_soup.find('meta', attrs={'name': 'description'})
            description = desc_meta.get('content', '').strip() if desc_meta else ""
            
            # Quick programmatic listicle/collection filter
            title_lower = title.lower()
            is_listicle = False
            if re.search(r'\b\d+\s*\+?\s*(?:best|delicious|easy|healthy|quick|favorite|great|ideas|recipes|meals|dinners)\b', title_lower):
                is_listicle = True
            elif any(kw in title_lower for kw in ['roundup', 'round-up', 'listicles', 'collection of', 'best recipes', 'favorite recipes']):
                is_listicle = True
                
            if is_listicle:
                print(f"[Recipe Finder] Programmatically rejected listicle/collection: {title}")
                continue

            # Check if URL already exists in Mealie
            if url in existing_urls:
                print(f"[Recipe Finder] Recipe URL already exists in Mealie: {url}. Skipping import.")
                return True
            
            # Validation prompt
            validation_prompt = (
                f"You are an expert in the 'Mealie Recipe Link Validator Skill'.\n\n"
                f"{_RECIPE_FINDER_SKILL_DEFINITION}\n\n"
                f"### CONTEXT FOR THIS INVOCATION:\n"
                f"URL: {url}\n"
                f"Title: {title}\n"
                f"Description: {description}\n\n"
                "Is this a single recipe?"
            )
            try:
                val_res = self.gemini.call(validation_prompt, expect_json=False).strip().upper()
                print(f"[Recipe Finder] Validation response for {url}: {val_res}")
                if "YES" in val_res:
                    # Link validated! Attempt Mealie Import.
                    print(f"[Recipe Finder] Link validated. Attempting to import into Mealie...")
                    payload = {
                        "url": url,
                        "includeCategories": True,
                        "includeTags": True
                    }
                    r = requests.post(f"{self.client.api_url}/api/recipes/create/url", json=payload, headers=self.client.headers, timeout=30)
                    if r.status_code in (200, 201):
                        resp_json = r.json()
                        slug = resp_json if isinstance(resp_json, str) else resp_json.get('slug')
                        
                        # Verify if the imported recipe has an image
                        try:
                            recipe_details = self.client.get_recipe_details(slug)
                            if not recipe_details.get('image'):
                                print(f"[Recipe Finder] Imported recipe '{slug}' has no image. Deleting and skipping...")
                                self.client.delete_recipe(recipe_details['id'])
                                continue
                                
                            # Automatically impute nutrition on new imports if missing/incomplete
                            db_nutrition = recipe_details.get('nutrition', {})
                            key_fields = ['calories', 'proteinContent', 'carbohydrateContent', 'fatContent', 'fiberContent', 'sodiumContent']
                            if not db_nutrition or any(db_nutrition.get(f) is None or db_nutrition.get(f) == "" or db_nutrition.get(f) == 0 or db_nutrition.get(f) == "0" for f in key_fields):
                                recipe_details = nutrition_imputer.impute_recipe_nutrition(recipe_details)
                        except Exception as img_err:
                            print(f"[Recipe Finder] Error verifying image or estimating nutrition for '{slug}': {img_err}")
                            continue

                        print(f"[Recipe Finder] Successfully imported recipe to Mealie with image. Slug: {slug}")
                        return True
                    else:
                        print(f"[Recipe Finder] Mealie import failed with status {r.status_code}: {r.text}")
            except Exception as e:
                print(f"[Recipe Finder] Error validating or importing link {url}: {e}")
                
        print("[Recipe Finder] Failed to find or import a recipe.")
        return False

    def get_recipes_from_api(self):
        """Fetch all recipes with their nutrition, tags, and ingredients from Mealie via API concurrently."""
        all_recipes_overview = self.client.get_all_recipes()
        detailed_recipes = []
        
        # Import parse_nutrient_val locally to avoid circular dependencies
        from .recipe_nutrition import parse_nutrient_val

        def fetch_details(r_overview):
            try:
                full_recipe = self.client.get_recipe_details(r_overview['id'])
                nutrition = full_recipe.get('nutrition', {})
                
                ingredients_list = []
                for ing in full_recipe.get('recipeIngredient', []):
                    note = ing.get('note') or ""
                    orig = ing.get('originalText') or ""
                    ing_text = f"{note} {orig}".strip()
                    if ing_text:
                        ingredients_list.append(ing_text.lower())
                
                instructions_list = [i.get('text', '').lower() for i in full_recipe.get('recipeInstructions', [])]
                
                return {
                    'id': full_recipe['id'],
                    'name': full_recipe['name'],
                    'slug': full_recipe.get('slug'),
                    'description': full_recipe.get('description'),
                    'calories': parse_nutrient_val(nutrition.get('calories')),
                    'fiber_content': parse_nutrient_val(nutrition.get('fiberContent')),
                    'protein_content': parse_nutrient_val(nutrition.get('proteinContent')),
                    'carbohydrate_content': parse_nutrient_val(nutrition.get('carbohydrateContent')),
                    'fat_content': parse_nutrient_val(nutrition.get('fatContent')),
                    'sodium_content': parse_nutrient_val(nutrition.get('sodiumContent')),
                    'sugar_content': parse_nutrient_val(nutrition.get('sugarContent')),
                    'cholesterol_content': parse_nutrient_val(nutrition.get('cholesterolContent')),
                    'tags': [t.get('name', '').lower() for t in full_recipe.get('tags', [])],
                    'ingredients': ingredients_list,
                    'instructions': instructions_list
                }
            except Exception as e:
                print(f"Error fetching detailed recipe for {r_overview.get('id', 'Unknown')}: {e}")
                return None

        # Fetch concurrently using a ThreadPoolExecutor with optimized workers count
        workers = min(4, len(all_recipes_overview) or 1)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            results = executor.map(fetch_details, all_recipes_overview)
            
        for res in results:
            if res is not None:
                detailed_recipes.append(res)
                
        return detailed_recipes

    def get_recipes_from_db(self):
        """Fetch all recipes with their nutrition, tags, and ingredients from Mealie using REST API."""
        return self.get_recipes_from_api()

    def check_blackstone_compatibility(self, recipe):
        """Check if a recipe uses the Blackstone griddle."""
        name_lower = recipe['name'].lower()
        instructions = recipe.get('recipeInstructions', [])
        instructions_text = " ".join([i.get('text', '').lower() for i in instructions if i.get('text')]).lower()
        
        return 'blackstone' in name_lower or 'griddle' in name_lower or 'blackstone' in instructions_text or 'griddle' in instructions_text
