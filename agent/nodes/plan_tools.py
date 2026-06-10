import json
import logging

from langchain_core.messages import ToolMessage

from agent.operators import Operator
from agent.state import AgentState, Filter, FilterGroup, QueryPlan
from agent.tools.create_filter import PLAN_TOOLS

logger = logging.getLogger(__name__)

_TOOLS_BY_NAME = {tool.name: tool for tool in PLAN_TOOLS}


def _apply_tool_action(groups: list[FilterGroup], payload: dict) -> str | None:
    action = payload.get("action")

    if action == "begin_group":
        logic = payload.get("logic", "and")
        groups.append(FilterGroup(logic=logic, filters=[]))
        return (
            f"Started {logic} filter group — call add_filter for each alternative "
            "in this same turn"
        )

    if action == "add_filter":
        if not groups:
            groups.append(FilterGroup(logic="and", filters=[]))

        filt = Filter(
            field=payload["field"],
            operator=Operator(payload["operator"]),
            value=payload["value"],
        )
        groups[-1].filters.append(filt)
        return f"Added filter: {filt.field} {filt.operator.value} {filt.value}"

    if action == "add_or_group":
        filters = [
            Filter(
                field=payload["field"],
                operator=Operator(payload["operator"]),
                value=value,
            )
            for value in payload["values"]
        ]
        groups.append(FilterGroup(logic="or", filters=filters))
        return f"Added OR group with {len(filters)} filters on {payload['field']}"

    if action == "add_mixed_or_group":
        filters = [
            Filter(
                field=item["field"],
                operator=Operator(item["operator"]),
                value=item["value"],
            )
            for item in payload["filters"]
        ]
        groups.append(FilterGroup(logic="or", filters=filters))
        return f"Added mixed OR group with {len(filters)} filters"

    if action == "error":
        return payload.get("message", "Invalid filter")

    return f"Unknown tool action: {action}"


def plan_tools_node(state: AgentState) -> AgentState:
    messages = state.get("messages") or []
    last = messages[-1]
    tool_calls = getattr(last, "tool_calls", None) or []

    existing_plan = state.get("data_query") or QueryPlan()
    groups = [group.model_copy(deep=True) for group in existing_plan.groups]

    tool_messages: list[ToolMessage] = []
    for call in tool_calls:
        tool = _TOOLS_BY_NAME.get(call["name"])
        if tool is None:
            result = json.dumps({"action": "error", "message": f"Unknown tool: {call['name']}"})
        else:
            try:
                result = tool.invoke(call["args"])
            except Exception as exc:
                result = json.dumps({"action": "error", "message": str(exc)})

        try:
            payload = json.loads(result)
            message = _apply_tool_action(groups, payload) or result
        except json.JSONDecodeError:
            message = result

        logger.info("Tool call: %s -> %s", call["args"], message)
        tool_messages.append(ToolMessage(content=message, tool_call_id=call["id"]))

    groups = [group for group in groups if group.filters]
    data_query = QueryPlan(groups=groups)
    logger.info("Updated plan: %s", data_query.model_dump())

    return {"messages": tool_messages, "data_query": data_query, "plan_reviewed": False}
