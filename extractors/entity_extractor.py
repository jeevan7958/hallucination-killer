
import os
import json
from groq import Groq
from dotenv import load_dotenv
from extractors.schema import ExtractionResult

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """
You are an expert knowledge graph builder.
Your job is to extract entities and relationships from text.

Rules:
1. Always use full canonical names. Never use pronouns or abbreviations.
2. Relationship types must be UPPER_SNAKE_CASE verbs. e.g. FOUNDED, WORKS_FOR, ACQUIRED
3. Only extract facts explicitly stated in the text. Never infer or assume.
4. Return ONLY valid JSON. No explanations, no markdown, no backticks.

JSON format:
{
  "products": [{"canonical_name": "", "category": "", "made_by": ""}],
  "concepts": [{"canonical_name": "", "description": ""}],
{
  "persons": [{"canonical_name": "", "aliases": [], "description": ""}],
  "organizations": [{"canonical_name": "", "aliases": [], "industry": ""}],
  "locations": [{"canonical_name": ""}],
  "relationships": [{"source": "", "target": "", "type": "", "year": null, "end_year": null, "notes": ""}]
}
"""

def extract_entities(text: str) -> ExtractionResult:
    """
    Takes raw text, sends to LLaMA, returns validated ExtractionResult.
    """
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Extract all entities and relationships from this text:\n\n{text}"}
        ],
        temperature=0.0  # Zero temperature = deterministic output. No creativity needed here.
    )

    raw = response.choices[0].message.content.strip()

    try:
        data = json.loads(raw)
        result = ExtractionResult(**data)
        return result
    except Exception as e:
        print(f"[ERROR] Failed to parse LLM output: {e}")
        print(f"[RAW OUTPUT]: {raw}")
        raise


if __name__ == "__main__":
    test_text = """
    Elon Musk co-founded OpenAI in 2015 alongside Sam Altman and Greg Brockman.
    The organization is headquartered in San Francisco, California.
    Musk later resigned from the OpenAI board in 2018.
    Sam Altman currently serves as CEO of OpenAI.
    """

    result = extract_entities(test_text)

    print("\n--- PERSONS ---")
    for p in result.persons:
        print(f"  {p.canonical_name} | aliases: {p.aliases}")

    print("\n--- ORGANIZATIONS ---")
    for o in result.organizations:
        print(f"  {o.canonical_name} | industry: {o.industry}")

    print("\n--- LOCATIONS ---")
    for l in result.locations:
        print(f"  {l.canonical_name}")

    print("\n--- RELATIONSHIPS ---")
    for r in result.relationships:
        print(f"  ({r.source}) --[{r.type}]--> ({r.target}) | year: {r.year}")

