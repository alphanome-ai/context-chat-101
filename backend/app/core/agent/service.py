from app.core.llm.schemas import InferenceRequest


class AgentNotImplementedError(Exception):
    pass


class AgentService:
    async def run(self, request: InferenceRequest) -> None:
        raise AgentNotImplementedError("Agent mode is not implemented yet.")
