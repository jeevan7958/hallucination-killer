import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from neo4j import GraphDatabase
from groq import Groq
from dotenv import load_dotenv
from retrievers.cypher_retriever import cypher_retrieve
import json

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

URI = os.getenv("NEO4J_URI")
USER = os.getenv("NEO4J_USER")
PASSWORD = os.getenv("NEO4J_PASSWORD")

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"

ANSWER_PROMPT = """
You are a precise question answering system backed by a Knowledge Graph.
You will be given:
1. A question
2. Graph facts retrieved from a Neo4j knowledge graph
3. Contradiction markers — facts that conflict with each other

Rules:
1. Answer ONLY based on the provided graph facts. Never use outside knowledge.
2. If contradictions exist, acknowledge them and explain the timeline.
3. Always cite which relationships support your answer.
4. If the graph facts are insufficient, say "The knowledge graph does not contain enough information to answer this question."
5. Be concise and precise.
"""

def get_contradictions(driver, entities: list[str]) -> list[dict]:
    """Fetches any known contradictions for the entities involved in the answer."""
    with driver.session() as session:
        result = session.run("""
            MATCH (c:ConflictMarker)
            WHERE c.person IN $entities OR c.org IN $entities
            RETURN c.person as person,
                   c.org as org,
                   c.rel_a as conflict_a,
                   c.rel_b as conflict_b
        """, entities=entities)
        return result.data()


def extract_entities_from_results(results: list[dict]) -> list[str]:
    """Pulls all entity names from cypher results for contradiction lookup."""
    entities = []
    for row in results:
        for value in row.values():
            if isinstance(value, str):
                entities.append(value)
    return list(set(entities))


def answer_question(question: str) -> str:
    """
    Full QA pipeline:
    1. Retrieve graph facts via Cypher
    2. Check for contradictions
    3. Send everything to LLaMA for grounded answer
    """
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

    print(f"\n[QUESTION] {question}")
    print("-" * 60)

    # Step 1: Graph retrieval
    retrieval = cypher_retrieve(question, driver)
    graph_facts = retrieval["results"]
    cypher_query = retrieval["query"]

    # Step 2: Contradiction check
    entities = extract_entities_from_results(graph_facts)
    contradictions = get_contradictions(driver, entities)

    driver.close()

    # Step 3: Build context for LLaMA
    context = f"""
GRAPH FACTS:
{json.dumps(graph_facts, indent=2)}

KNOWN CONTRADICTIONS:
{json.dumps(contradictions, indent=2) if contradictions else "None detected."}

CYPHER QUERY USED:
{cypher_query}
"""

    print(f"\n  [CONTEXT SENT TO LLM]\n{context}")

    # Step 4: Generate grounded answer
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": ANSWER_PROMPT},
            {"role": "user", "content": f"Question: {question}\n\n{context}"}
        ],
        temperature=0.0
    )

    answer = response.choices[0].message.content.strip()
    return answer


if __name__ == "__main__":
    questions = [
        "Who founded OpenAI?",
        "Is Sam Altman currently the CEO of OpenAI?",
        "Why did Elon Musk leave OpenAI?",
        "What happened to Greg Brockman at OpenAI?",
    ]

    for question in questions:
        answer = answer_question(question)
        print(f"\n[ANSWER]\n{answer}")
        print("=" * 60)
