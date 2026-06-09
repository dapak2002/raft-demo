from langchain_openai import ChatOpenAI

from config import MODEL, OPENROUTER_API_KEY, OPENROUTER_BASE_URL


def get_llm() -> ChatOpenAI:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    return ChatOpenAI(
        model=MODEL,
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        temperature=0,
    )
