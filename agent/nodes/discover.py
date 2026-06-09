import logging
from typing import Any

from agent.schema import Record
from agent.state import AgentState

logger = logging.getLogger(__name__)


def discover_node(state: AgentState) -> dict[str, Any]:
    records = state["records"]
    logger.info("Node: discover")

    buckets: dict[str, set[str]] = {}
    for record in records:
        for key, val in record.fields.items():
            norm = Record.normalize_key(key)
            if not norm:
                continue
            buckets.setdefault(norm, set())
            if isinstance(val, list):
                buckets[norm].update(str(item) for item in val)
            else:
                buckets[norm].add(str(val))

    lines = [
        f"- {name}: {', '.join(sorted(values)[:15])}"
        for name, values in sorted(buckets.items())
    ]
    field_samples = "\n".join(lines)
    logger.info("Field samples:\n%s", field_samples)
    return {"field_samples": field_samples}
