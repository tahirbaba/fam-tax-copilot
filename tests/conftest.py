import os

# Tests never call the real API.
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
os.environ["FAMCHECK_MODE"] = "replay"
