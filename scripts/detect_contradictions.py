import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

URI = os.getenv("NEO4J_URI")
USER = os.getenv("NEO4J_USER")
PASSWORD = os.getenv("NEO4J_PASSWORD")

# Pairs of relationships that contradict each other
CONTRADICTING_PAIRS = [
    ("FIRED_FROM",    "REINSTATED_AT"),
    ("FOUNDED",       "RESIGNED_FROM"),
    ("IS_CEO_OF",     "FIRED_FROM"),
]

def detect_and_mark_contradictions(driver):
    """
    Finds entities that have contradicting relationships
    and creates a CONTRADICTS edge between them.
    This is what makes our graph smarter than vector RAG —
    instead of randomly picking one fact, we explicitly
    encode the conflict and let the LLM reason over both.
    """
    with driver.session() as session:
        for rel_a, rel_b in CONTRADICTING_PAIRS:
            result = session.run("""
                MATCH (person)-[r1:RELATED {type: $rel_a}]->(org)
                MATCH (person)-[r2:RELATED {type: $rel_b}]->(org)
                MERGE (r1_node:ConflictMarker {
                    person: person.canonical_name,
                    org: org.canonical_name,
                    rel_a: $rel_a,
                    rel_b: $rel_b
                })
                RETURN person.canonical_name as person,
                       org.canonical_name as org,
                       $rel_a as conflict_a,
                       $rel_b as conflict_b
            """, rel_a=rel_a, rel_b=rel_b)

            records = result.data()
            for record in records:
                print(f"  [CONFLICT DETECTED]")
                print(f"    {record['person']} → {record['conflict_a']} + {record['conflict_b']} → {record['org']}")
                print(f"    This is a temporal contradiction — both facts are true at different times.")
                print()

    print("[DONE] Contradiction detection complete.")


def print_contradiction_summary(driver):
    """
    Prints a summary of all detected contradictions.
    This is what the final QA system will use to give
    grounded, nuanced answers instead of hallucinating.
    """
    with driver.session() as session:
        result = session.run("""
            MATCH (c:ConflictMarker)
            RETURN c.person as person,
                   c.org as org,
                   c.rel_a as conflict_a,
                   c.rel_b as conflict_b
        """)

        records = result.data()

        if not records:
            print("No contradictions found in the graph.")
            return

        print("\n--- CONTRADICTION SUMMARY ---")
        print(f"Total conflicts found: {len(records)}\n")
        for r in records:
            print(f"  Entity  : {r['person']}")
            print(f"  Target  : {r['org']}")
            print(f"  Tension : {r['conflict_a']} ←→ {r['conflict_b']}")
            print()


if __name__ == "__main__":
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

    print("[START] Scanning graph for contradictions...\n")
    detect_and_mark_contradictions(driver)
    print_contradiction_summary(driver)

    driver.close()
