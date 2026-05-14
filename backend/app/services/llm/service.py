from app.core.config import get_settings
from app.services.llm.schemas import LLMModel, LLMProviderInfo, ProvidersResponse


class LLMService:
    def list_providers(self) -> ProvidersResponse:
        settings = get_settings()
        models = [
            LLMModel(
                id=model_id,
                name=model_id,
                isDefault=model_id == settings.llm_default_model,
            )
            for model_id in settings.llm_available_models
        ]

        return ProvidersResponse(
            providers=[
                LLMProviderInfo(
                    id="openai",
                    name=settings.llm_provider_name,
                    type="openai-compatible",
                    models=models,
                )
            ]
        )
