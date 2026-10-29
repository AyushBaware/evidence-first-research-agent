import os
import sys
from dotenv import load_dotenv

load_dotenv()  # reads the .env file into environment variables

print("Python:", sys.version.split()[0])


def check_env(name):
    is_set = bool(os.getenv(name))
    print(f"{name}: {'set' if is_set else 'MISSING'}")
    return is_set


check_env("GEMINI_API_KEY")
check_env("GROQ_API_KEY")
check_env("TAVILY_API_KEY")

# 1) Both LLM providers through the same OpenAI SDK
from openai import OpenAI

# name: (base_url, env var holding the key, model name)
# Model names change over time; if one fails with "model not found",
# check the current name in the Gemini/Groq console and edit it here.
PROVIDERS = {
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY", "<flash model from the list>"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", "openai/gpt-oss-120b"),
}

for name, (base_url, key_var, model) in PROVIDERS.items():
    try:
        client = OpenAI(base_url=base_url, api_key=os.getenv(key_var))
        reply = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply with the single word: ok"}],
        )
        print(f"{name} -> {reply.choices[0].message.content!r}")
    except Exception as e:
        print(f"{name} FAILED: {e}")

# 2) Search tool
from tavily import TavilyClient

try:
    results = TavilyClient(api_key=os.getenv("TAVILY_API_KEY")).search(
        "open source vector database", max_results=2
    )
    print("tavily ->", len(results["results"]), "results")
except Exception as e:
    print("tavily FAILED:", e)

# 3) Page text extractor
import trafilatura

print("trafilatura -> imported OK")