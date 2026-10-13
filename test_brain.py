import time
from google import genai
from google.genai import errors

client = genai.Client()   # reads GEMINI_API_KEY

# Try the first model; if it is busy, try the next one
MODELS = ["gemini-3.8-flash", "gemini-3.8-flash-lite"]

def ask_brain(prompt, retries=3):
    for model in MODELS:
        for attempt in range(retries):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                )
                print(f"(answered by {model})")
                return response.text
            except errors.ServerError as e:
                print(f"{model} busy (attempt {attempt + 1}/{retries}), waiting...")
                time.sleep(2 * (attempt + 1))   # wait 2s, 4s, 6s
    return "Sorry, the brain is too busy right now. Try again soon."

print(ask_brain("Say hello and introduce yourself as Jarvis in one sentence."))