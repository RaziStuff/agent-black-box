from agent_black_box.adapters.langgraph import LangGraphRecorder


def load_ticket(state):
    ticket_id = state["ticket_id"]
    return {
        **state,
        "ticket": {
            "ticket_id": ticket_id,
            "customer": "Ada",
            "topic": "refund",
            "amount": 199,
        },
    }


def decide_next(state):
    ticket = state["ticket"]
    decision = "manual_review" if ticket["amount"] > 100 else "approve"
    return {**state, "decision": decision}


def draft_reply(state):
    return {
        **state,
        "reply": f"Ticket {state['ticket_id']} needs {state['decision'].replace('_', ' ')}.",
    }


def main():
    recorder = LangGraphRecorder(name="langgraph-node-demo")
    try:
        load = recorder.wrap_node(load_ticket)
        decide = recorder.wrap_node(decide_next)
        draft = recorder.wrap_node(draft_reply)

        state = {"ticket_id": "tkt_1042"}
        for node in (load, decide, draft):
            state = node(state)

        recorder.end_run("ok")
        print(state["reply"])
        print(f"Recorded LangGraph node run: {recorder.abb_run_id}")
    finally:
        recorder.close()


if __name__ == "__main__":
    main()
