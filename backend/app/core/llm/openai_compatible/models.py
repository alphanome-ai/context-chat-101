from app.core.llm.openai_compatible.chat_completions import OpenAIChatCompletionsModel
from app.core.llm.openai_compatible.responses import OpenAIResponsesModel


class GPT52ChatModel(OpenAIChatCompletionsModel):
    unsupported_payload_fields = frozenset({"temperature"})


class GPT55Model(OpenAIResponsesModel):
    unsupported_payload_fields = frozenset({"temperature"})
    reasoning_effort = "medium"
    reasoning_summary = "auto"


class GPT53CodexModel(OpenAIResponsesModel):
    unsupported_payload_fields = frozenset({"temperature", "top_p"})
    reasoning_effort = "medium"
    reasoning_summary = "auto"


class GPT52Model(OpenAIChatCompletionsModel):
    pass


class KimiK26Model(OpenAIChatCompletionsModel):
    pass
