import os
import json
import requests

class GeminiClient:
    def __init__(self, api_key=None, model_name=None):
        self.api_key = api_key or os.getenv('GOOGLE_API_KEY')
        self.model = model_name or os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')
        if not self.api_key:
            raise RuntimeError("GOOGLE_API_KEY is not set in environment.")

    def call(self, prompt: str, expect_json: bool = True, temperature: float = 0.2, thinking_budget: int = 0) -> str:
        """
        Send a prompt to the Gemini API and return the text response.
        If expect_json=True, requests JSON output mode and returns the raw text
        so callers can parse it themselves.
        """
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json" if expect_json else "text/plain",
                "thinkingConfig": {
                    "thinkingBudget": thinking_budget
                }
            }
        }

        print("--- AI PROMPT ---")
        print(prompt)
        print("-------------------")

        resp = requests.post(url, json=payload, timeout=180)
        resp.raise_for_status()
        data = resp.json()
        print("--- AI RAW RESPONSE ---")
        print(json.dumps(data, indent=2))
        print("-----------------------")
        return data["candidates"][0]["content"]["parts"][0]["text"]

def call_gemini(prompt: str, expect_json: bool = True, temperature: float = 0.2, thinking_budget: int = 0) -> str:
    """Compatibility wrapper function."""
    client = GeminiClient()
    return client.call(prompt, expect_json, temperature, thinking_budget)
