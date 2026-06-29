import time

from agent_black_box import annotate, record, record_event, span, tool


@tool
def load_ticket(ticket_id):
    time.sleep(0.02)
    return {
        "ticket_id": ticket_id,
        "customer": "Ada Lovelace",
        "request": "Refund the duplicate annual subscription charge.",
        "amount_usd": 199,
    }


@tool
def check_policy(ticket):
    time.sleep(0.02)
    if ticket["amount_usd"] > 100:
        return {"decision": "manual_review", "reason": "Refund exceeds self-serve threshold"}
    return {"decision": "approve", "reason": "Within self-serve threshold"}


@tool
def draft_reply(ticket, policy):
    time.sleep(0.02)
    return (
        f"Hi {ticket['customer']}, thanks for flagging this. "
        f"I found the duplicate charge and routed it for {policy['decision']}."
    )


def main():
    with record("refund-triage-demo", tags=["demo", "local"]):
        annotate("Demo run started")
        ticket = load_ticket("ticket_001")
        policy = check_policy(ticket)

        with span(
            "mock model reasoning",
            type="model.call",
            attributes={
                "provider": "local-demo",
                "model": "mock-agent-v0",
                "input_tokens": 71,
                "output_tokens": 33,
            },
        ):
            record_event(
                "message.created",
                message="The safest path is manual review because the amount is above threshold.",
                attributes={"role": "assistant"},
            )

        reply = draft_reply(ticket, policy)
        record_event("agent.final", message=reply, attributes={"decision": policy["decision"]})
        print(reply)


if __name__ == "__main__":
    main()

