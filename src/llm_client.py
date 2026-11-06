"""
llm_client.py: the ONE place the project talks to an AI model.

Every provider below speaks the OpenAI chat format, so we use the `openai`
library for all of them and only swap base_url + key. To change model or
provider, edit .env; no code changes needed.
"""
import os
import threading
import time

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()  # copies the values in .env into environment variables

PROVIDERS = {
    "gemini":    {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai/", "key_env": "GEMINI_API_KEY"},
    "groq":      {"base_url": "https://api.groq.com/openai/v1",                         "key_env": "GROQ_API_KEY"},
    "openai":    {"base_url": "https://api.openai.com/v1",                              "key_env": "OPENAI_API_KEY"},
    "anthropic": {"base_url": "https://api.anthropic.com/v1/",                          "key_env": "ANTHROPIC_API_KEY"},
}

# running totals so we can report cost at the end of a run
USAGE = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
_usage_lock = threading.Lock()   # several threads may update USAGE at once


def get_client(provider=None):
    """Build an API client for the chosen provider (default: LLM_PROVIDER in .env)."""
    provider = (provider or os.getenv("LLM_PROVIDER", "gemini")).lower()
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider '{provider}'. Choose one of: {list(PROVIDERS)}")
    cfg = PROVIDERS[provider]
    api_key = os.getenv(cfg["key_env"])
    if not api_key:
        raise RuntimeError(f"{cfg['key_env']} is missing. Add it to your .env file.")
    return OpenAI(api_key=api_key, base_url=cfg["base_url"]), provider


def current_model(model=None):
    """The model name we will use: explicit argument wins, else LLM_MODEL from .env."""
    model = model or os.getenv("LLM_MODEL")
    if not model:
        raise RuntimeError("LLM_MODEL is missing in .env. Run check_key.py to see available models.")
    return model


def chat(prompt, system="You are a helpful assistant.", model=None, provider=None,
         temperature=0.2, json_mode=False, retries=3):
    """Send one prompt, get the reply text back. Retries on temporary failures."""
    client, provider = get_client(provider)
    model = current_model(model)
    extra = {"response_format": {"type": "json_object"}} if json_mode else {}

    for attempt in range(1, retries + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": prompt}],
                temperature=temperature,
                **extra,
            )
            if resp.usage:
                with _usage_lock:
                    USAGE["calls"] += 1
                    USAGE["input_tokens"] += resp.usage.prompt_tokens or 0
                    USAGE["output_tokens"] += resp.usage.completion_tokens or 0
            return resp.choices[0].message.content
        except Exception as e:
            if attempt == retries:
                raise
            is_rate_limit = "429" in str(e) or "RateLimit" in type(e).__name__
            wait = (2 ** attempt) * (5 if is_rate_limit else 1)  # rate limits: 10s, 20s, 40s, 80s
            print(f"  [llm_client] attempt {attempt} failed ({type(e).__name__}: {e}). Retrying in {wait}s...")
            time.sleep(wait)