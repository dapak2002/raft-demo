#!/usr/bin/env python3
import argparse
import json
import logging
import sys

from agent.graph import run

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
        result = run(query)
        print(json.dumps(result, indent=2))
        if result.get("status") == "error":
            sys.exit(1)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
