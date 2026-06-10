#!/usr/bin/env python3
import argparse
import json
import logging
import sys

from agent.graph import run
from agent.tools.fetch_orders import FetchError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the agent graph.")
    parser.add_argument("query", nargs="?", help="Natural language query")
    args = parser.parse_args()

    query = args.query or input("Enter your query: ").strip()
    if not query:
        print("No query provided", file=sys.stderr)
        sys.exit(1)

    try:
        print(json.dumps(run(query), indent=2))
    except FetchError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
