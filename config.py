import os

from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MODEL = "openai/gpt-oss-120b:exacto"
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))

CUSTOMER_API_URL = os.getenv("CUSTOMER_API_URL", "http://localhost:5001")
FETCH_TIMEOUT_SECONDS = int(os.getenv("FETCH_TIMEOUT_SECONDS", "30"))

# LangGraph per-node fault tolerance (retries/timeouts are in addition to HTTP/LLM client limits)
NODE_MAX_RETRIES = int(os.getenv("NODE_MAX_RETRIES", str(LLM_MAX_RETRIES)))
FETCH_NODE_TIMEOUT_SECONDS = int(
    os.getenv("FETCH_NODE_TIMEOUT_SECONDS", str(FETCH_TIMEOUT_SECONDS + 15))
)
LLM_NODE_TIMEOUT_SECONDS = int(
    os.getenv("LLM_NODE_TIMEOUT_SECONDS", str(LLM_TIMEOUT_SECONDS + 30))
)
PARSE_MAX_CHARS = int(os.getenv("PARSE_MAX_CHARS", "4000"))
PARSE_CHUNK_OVERLAP = int(os.getenv("PARSE_CHUNK_OVERLAP", "500"))
PARSE_MAX_WORKERS = int(os.getenv("PARSE_MAX_WORKERS", "5"))
MAX_PLAN_ATTEMPTS = int(os.getenv("MAX_PLAN_ATTEMPTS", "3"))
