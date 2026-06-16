from openai import OpenAI
from fastmcp import FastMCP
from api.config import config


openai_client = OpenAI(
    base_url=config.OPENAI_API_URL,
    api_key=config.OPENAI_API_KEY,
)


mcp = FastMCP(
    "Meditron",
    instructions="Provides an interface to the medical LLM Meditron, trained on a comprehensively curated medical corpus, including selected PubMed papers and abstracts, a dataset of internationally-recognized medical guidelines, and a general domain corpus. Knowledge cutoff is August 2023.",
)


@mcp.tool
def ask(prompt: str, system_prompt: str = "") -> str:
    """Ask something to the Meditron LLM."""

    response = openai_client.responses.create(
        model=config.MEDITRON_MODEL_NAME,
        instructions=system_prompt,
        input=prompt,
    )

    return response.output_text


@mcp.prompt
def system_prompt_medical_q_and_a() -> str:
    """A system prompt for medical Q&A."""

    return "You are a medical expert with deep knowledge of clinical science, medical guidelines, and evidence-based medicine. Answer the following question based on current standard medical practices. If uncertain, acknowledge the uncertainty rather than guessing"


def main() -> None:
    mcp.run


if __name__ == "__main__":
    main()
