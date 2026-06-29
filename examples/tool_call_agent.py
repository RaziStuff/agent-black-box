from agent_black_box.adapters.tools import ToolCallRecorder


def lookup_policy(topic: str, amount: int):
    """Look up the support policy for a ticket."""
    return {
        "topic": topic,
        "limit": 100,
        "requires_review": amount > 100,
    }


def create_ticket_note(ticket_id: str, note: str):
    """Create a ticket note."""
    return {"ticket_id": ticket_id, "note_id": "note_001", "body": note}


def main():
    recorder = ToolCallRecorder(name="tool-call-demo")
    try:
        lookup = recorder.wrap_tool(lookup_policy)
        create_note = recorder.wrap_tool(
            create_ticket_note,
            schema={
                "name": "create_ticket_note",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "ticket_id": {"type": "string"},
                        "note": {"type": "string"},
                    },
                    "required": ["ticket_id", "note"],
                },
            },
        )

        policy = lookup("refund", amount=199)
        note = create_note("tkt_1042", "Refund needs manual review.")
        recorder.record_mcp_tool_call(
            "knowledge.search",
            {"query": "refund review policy"},
            {"matches": [{"title": "Refund policy", "score": 0.91}]},
            request_id="mcp_req_001",
            schema={
                "name": "knowledge.search",
                "inputSchema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        )
        recorder.end_run("ok")
        print(f"Policy requires review: {policy['requires_review']}")
        print(f"Created note: {note['note_id']}")
        print(f"Recorded tool call run: {recorder.abb_run_id}")
    finally:
        recorder.close()


if __name__ == "__main__":
    main()
