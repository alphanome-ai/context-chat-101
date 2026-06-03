import os

from dotenv import load_dotenv
from rlm import RLM

load_dotenv()

deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
if not deployment:
    raise RuntimeError(
        "Set AZURE_OPENAI_DEPLOYMENT in backend/.env to your Azure OpenAI deployment "
        "name. For Azure, this is the deployment name in your Azure resource, not "
        "necessarily the model name."
    )

rlm = RLM(
    backend="azure_openai",
    backend_kwargs={"model_name": deployment},
    verbose=True,  # For printing to console with rich, disabled by default.
)

print(rlm.completion("Print me the first 100 powers of two, each on a newline.").response)
