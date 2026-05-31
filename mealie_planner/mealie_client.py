import os
import json
import requests

def get_mealie_token():
    """Retrieve the API token from the MEALIE_TOKEN env var."""
    token = os.getenv('MEALIE_TOKEN')
    if token and token != 'your_mealie_api_token_here':
        return token

    raise RuntimeError("Mealie auth token could not be retrieved from MEALIE_TOKEN environment variable.")

class MealieClient:
    def __init__(self):
        self.api_url = os.getenv('MEALIE_API_URL', 'http://mealie:9000')
        self.token = get_mealie_token()
        if not self.token:
            raise Exception("Mealie API Token could not be retrieved. Please check your DB or environment.")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        self._recipe_details_cache = {}

    def get_users(self):
        """Fetch all users registered in Mealie using the admin endpoint."""
        r = requests.get(f"{self.api_url}/api/admin/users", headers=self.headers)
        r.raise_for_status()
        return r.json().get('items', [])

    def get_all_recipes(self):
        """Fetch all recipes from Mealie."""
        r = requests.get(f"{self.api_url}/api/recipes?perPage=200", headers=self.headers)
        r.raise_for_status()
        return r.json().get('items', [])

    def get_recipe_details(self, recipe_id):
        """Fetch full details of a specific recipe, using a cache."""
        if recipe_id in self._recipe_details_cache:
            return self._recipe_details_cache[recipe_id]

        r = requests.get(f"{self.api_url}/api/recipes/{recipe_id}", headers=self.headers, timeout=10)
        r.raise_for_status()
        details = r.json()
        self._recipe_details_cache[recipe_id] = details
        return details

    def get_shopping_list_items(self, list_id):
        """Fetch all items currently on a shopping list."""
        r = requests.get(f"{self.api_url}/api/households/shopping/lists/{list_id}", headers=self.headers)
        r.raise_for_status()
        return r.json().get('listItems', [])

    def clear_shopping_list(self, list_id):
        """Delete all items from a shopping list using Mealie's bulk delete endpoint."""
        items = self.get_shopping_list_items(list_id)
        if not items:
            return
        item_ids = [item['id'] for item in items]
        
        # Chunk requests to prevent extremely long URL queries
        chunk_size = 50
        for i in range(0, len(item_ids), chunk_size):
            chunk = item_ids[i:i+chunk_size]
            r = requests.delete(f"{self.api_url}/api/households/shopping/items", params={"ids": chunk}, headers=self.headers)
            r.raise_for_status()

    def add_shopping_list_items_bulk(self, items):
        """Add multiple items to the shopping list in bulk."""
        if not items:
            return
        r = requests.post(f"{self.api_url}/api/households/shopping/items/create-bulk", json=items, headers=self.headers)
        r.raise_for_status()

    def update_shopping_list_item(self, item_id, payload):
        """Update a specific shopping list item."""
        # Mealie often expects the full item object or specific fields.
        # For 'checked', sending just {"checked": bool} to the item endpoint is usually enough.
        r = requests.put(f"{self.api_url}/api/households/shopping/items/{item_id}", json=payload, headers=self.headers)
        r.raise_for_status()

    def get_labels(self):
        """Fetch all multi-purpose labels."""
        r = requests.get(f"{self.api_url}/api/groups/labels", headers=self.headers)
        r.raise_for_status()
        return r.json().get('items', [])

    def create_label(self, name, color="#959595"):
        """Create a new shopping label."""
        payload = {"name": name, "color": color}
        r = requests.post(f"{self.api_url}/api/groups/labels", json=payload, headers=self.headers)
        r.raise_for_status()
        return r.json()

    def get_meal_plan(self, start_date, end_date):
        """Fetch scheduled meal plans for a date range."""
        r = requests.get(f"{self.api_url}/api/households/mealplans?startDate={start_date}&endDate={end_date}", headers=self.headers)
        r.raise_for_status()
        return r.json().get('items', [])

    def schedule_meal(self, date_str, entry_type, title="", text="", recipe_id=None):
        """Schedule a meal plan entry."""
        # Mealie 422 fix: If recipeId is None, title MUST NOT be empty.
        # It's treated as a 'Note' entry.
        if not recipe_id and not title:
            title = "Planned Meal"

        payload = {
            "date": date_str,
            "entryType": entry_type,
            "title": title,
            "text": text,
            "recipeId": recipe_id
        }
        print(f"[Mealie] Scheduling {entry_type} on {date_str}: {title or recipe_id}")
        r = requests.post(f"{self.api_url}/api/households/mealplans", json=payload, headers=self.headers)
        if r.status_code == 422:
            print(f"[Mealie] 422 Error Payload: {json.dumps(payload)}")
            print(f"[Mealie] 422 Error Response: {r.text}")
        r.raise_for_status()

    def delete_meal_plan_entry(self, entry_id):
        """Delete a meal plan entry by ID."""
        requests.delete(f"{self.api_url}/api/households/mealplans/{entry_id}", headers=self.headers)

    def delete_recipe(self, recipe_id):
        """Delete a recipe by ID."""
        r = requests.delete(f"{self.api_url}/api/recipes/{recipe_id}", headers=self.headers)
        r.raise_for_status()
