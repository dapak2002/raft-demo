#!/usr/bin/env python3
import argparse
import json
import logging
import sys

from agent.tools import FetchError
from agent.graph import run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Query customer orders with natural language.")
    parser.add_argument("query", nargs="?", help="Natural language query")
    parser.add_argument("--limit", type=int, default=None, help="Limit passed to customer API")
    args = parser.parse_args()

    query = args.query or input("Enter your query: ").strip()
    if not query:
        logger.error("No query provided")
        sys.exit(1)

    try:
        print(json.dumps(run(query, limit=args.limit), indent=2))
    except FetchError as exc:
        logger.error("%s", exc)
        sys.exit(1)
    except RuntimeError as exc:
        logger.error("%s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
