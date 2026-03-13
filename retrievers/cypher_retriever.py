import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from neo4j import GraphDatabase
from groq import Groq
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

URI = os.getenv("NEO4J_URI")
USER = os.getenv("NEO4J_USER")
PASSWORD = os.getenv("NEO4J_PASSWORD")

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"

CYPHER_GENERATION_PROMPT = """
You are an expert Neo4j Cypher query writer.
Given a question, write a Cypher query to retrieve relevant facts from the graph.

Graph Schema:
- Nodes: Person {canonical_name}, Organization {canonical_name}, Location {canonical_name}, Product {canonical_name, category, made_by}, Concept {canonical_name, description}
- Relationships: All stored as RELATED edges with a 'type' property
- Relationship types include: FOUNDED, RESIGNED_FROM, FIRED_FROM, REINSTATED_AT, IS_CEO_OF, INVESTED_IN, HEADQUARTERED_IN

Rules:
1. Always use MATCH, never CREATE or DELETE
2. Always RETURN canonical_name properties, not entire nodes
3. Always alias the relationship as [r:RELATED] when you need to access its properties
4. Use r.type to access relationship type, never use type(r)
5. Keep queries simple — one or two hops maximum
6. Return ONLY the Cypher query, no explanation, no backticks

Example:
Question: Who founded OpenAI?
Query: MATCH (p:Person)-[r:RELATED {type: 'FOUNDED'}]->(o:Organization {canonical_name: 'OpenAI'}) RETURN p.canonical_name as person, r.type as relationship, o.canonical_name as organization
"""

CYPHER_FIX_PROMPT = """
You are an expert Neo4j Cypher query debugger.
The following Cypher query failed with an error. Fix it and return ONLY the corrected query.
No explanation, no backticks.

Failed Query: {query}
Error: {error}

Remember:
- Always alias relationships as [r:RELATED]
- Use r.type not type(r)
- Never reference undefined variables
"""

def generate_cypher(question: str) -> str:
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": CYPHER_GENERATION_PROMPT},
            {"role": "user", "content": f"Question: {question}"}
        ],
        temperature=0.0
    )
    return response.choices[0].message.content.strip()


def fix_cypher(query: str, error: str) -> str:
    """Self-healing: asks LLaMA to fix a broken Cypher query."""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": CYPHER_FIX_PROMPT.format(
                query=query, error=error
            )},
            {"role": "user", "content": "Fix this query."}
        ],
        temperature=0.0
    )
    return response.choices[0].message.content.strip()


def run_cypher(query: str, driver) -> tuple[list[dict], str | None]:
    """Returns (results, error_message)."""
    try:
        with driver.session() as session:
            result = session.run(query)
            return result.data(), None
    except Exception as e:
        return [], str(e)


def cypher_retrieve(question: str, driver) -> dict:
    """
    Full cypher retrieval pipeline with self-healing.
    If the first query fails, automatically fixes and retries once.
    """
    print(f"  [CYPHER] Generating query for: {question}")
    query = generate_cypher(question)
    print(f"  [CYPHER] Query: {query}")

    results, error = run_cypher(query, driver)

    # Self-healing retry
    if error:
        print(f"  [CYPHER ERROR] {error}")
        print(f"  [CYPHER] Attempting self-heal...")
        query = fix_cypher(query, error)
        print(f"  [CYPHER] Fixed Query: {query}")
        results, error = run_cypher(query, driver)
        if error:
            print(f"  [CYPHER] Self-heal failed: {error}")
            results = []

    print(f"  [CYPHER] Found {len(results)} results")
    return {"query": query, "results": results}

