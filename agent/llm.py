from langchain_openai import ChatOpenAI

from config import (
    LLM_MAX_RETRIES,
    LLM_TIMEOUT_SECONDS,
    MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
)


def get_llm() -> ChatOpenAI:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    return ChatOpenAI(
        model=MODEL,
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        temperature=0,
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=LLM_MAX_RETRIES,
    )
