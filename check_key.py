"""
check_key.py: confirms your API key works BEFORE we build anything.
Step 1 lists the models your key can use; step 2 sends a tiny test prompt.
"""
import os
import sys

from src.llm_client import get_client, chat


def main():
    client, provider = get_client()
    print(f"Provider: {provider}")

    print("Step 1/2: listing models your key can access...")
    try:
        models = sorted(m.id.removeprefix("models/") for m in client.models.list())
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")
        print("  -> Usually a wrong/expired key, wrong provider, or no billing/quota left.")
        sys.exit(1)
    print(f"  Found {len(models)} models:")
    for m in models[:60]:
        print("   -", m)

    model = os.getenv("LLM_MODEL")
    if not model:
        print("\nLLM_MODEL is empty in .env. Pick a model from the list above, add it, run again.")
        sys.exit(0)

    print(f"\nStep 2/2: sending a tiny test prompt to '{model}'...")
    reply = chat('Reply with exactly this JSON: {"status": "ok"}', json_mode=True)
    print("  Reply:", reply)
    print("\nKey works. Ready for Step 2.")


if __name__ == "__main__":
    main()