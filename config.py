import os

from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MODEL = "openai/gpt-oss-120b:exacto"

CUSTOMER_API_URL = os.getenv("CUSTOMER_API_URL", "http://localhost:5001")
FETCH_TIMEOUT_SECONDS = int(os.getenv("FETCH_TIMEOUT_SECONDS", "30"))
FETCH_PAGE_SIZE = int(os.getenv("FETCH_PAGE_SIZE", "100"))
PARSE_MAX_CHARS = int(os.getenv("PARSE_MAX_CHARS", "4000"))
PARSE_CHUNK_OVERLAP = int(os.getenv("PARSE_CHUNK_OVERLAP", "500"))
