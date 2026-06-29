from agent_black_box.adapters.langchain import AgentBlackBoxCallbackHandler


def main():
    handler = AgentBlackBoxCallbackHandler(name="langchain-callback-demo")
    try:
        handler.on_chain_start({"name": "AgentExecutor"}, {"input": "check refund policy"}, run_id="chain-demo")
        handler.on_llm_start(
            {"name": "ChatOpenAI", "kwargs": {"model_name": "demo-model"}},
            ["Decide whether to approve a refund"],
            run_id="llm-demo",
            parent_run_id="chain-demo",
        )
        handler.on_llm_end(
            {
                "generations": [[{"text": "Refund needs manual review."}]],
                "llm_output": {
                    "token_usage": {
                        "prompt_tokens": 15,
                        "completion_tokens": 8,
                        "total_tokens": 23,
                    }
                },
            },
            run_id="llm-demo",
        )
        handler.on_tool_start(
            {"name": "lookup_policy"},
            "refund amount: 199",
            run_id="tool-demo",
            parent_run_id="chain-demo",
        )
        handler.on_tool_end({"decision": "manual_review"}, run_id="tool-demo")
        handler.on_chain_end({"output": "Manual review required."}, run_id="chain-demo")
        print(f"Recorded LangChain callback run: {handler.abb_run_id}")
    finally:
        handler.close()


if __name__ == "__main__":
    main()
