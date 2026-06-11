import os

from dotenv import load_dotenv

load_dotenv()

# Environment (secrets and deployment-specific URLs)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
CUSTOMER_API_URL = os.getenv("CUSTOMER_API_URL", "http://localhost:5001")

# OpenRouter
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MODEL = "openai/gpt-oss-120b:exacto"
LLM_TIMEOUT_SECONDS = 60
LLM_MAX_RETRIES = 3

# Customer API fetch
FETCH_TIMEOUT_SECONDS = 30

# LangGraph per-node fault tolerance (retries/timeouts are in addition to HTTP/LLM client limits)
NODE_MAX_RETRIES = LLM_MAX_RETRIES
FETCH_NODE_TIMEOUT_SECONDS = FETCH_TIMEOUT_SECONDS + 15
LLM_NODE_TIMEOUT_SECONDS = LLM_TIMEOUT_SECONDS + 30

# Parse windowing
PARSE_MAX_CHARS = 4000
PARSE_CHUNK_OVERLAP = 500
PARSE_MAX_WINDOWS = 20
PARSE_MAX_WORKERS = 5
MAX_PLAN_ATTEMPTS = 3

# LLM prompt bounds (context-window hardening)
USER_QUERY_MAX_CHARS = 2000
PLAN_MAX_TOOL_TURNS = 8
PLAN_FEEDBACK_MAX_CHARS = 500
REVIEW_PLAN_MAX_JSON_CHARS = 8000
