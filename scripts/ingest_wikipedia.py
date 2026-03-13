
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import wikipediaapi
from neo4j import GraphDatabase
from dotenv import load_dotenv
from scripts.ingest_documents import ingest_document_text
from scripts.normalize_relationships import normalize
from scripts.detect_contradictions import detect_and_mark_contradictions

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

URI = os.getenv("NEO4J_URI")
USER = os.getenv("NEO4J_USER")
PASSWORD = os.getenv("NEO4J_PASSWORD")

wiki = wikipediaapi.Wikipedia(
    language='en',
    user_agent='HallucinationKiller/1.0'
)

def fetch_wikipedia_page(topic: str) -> str | None:
    """Fetches the summary text of a Wikipedia page."""
    page = wiki.page(topic)
    if not page.exists():
        print(f"  [WARNING] Wikipedia page not found: {topic}")
        return None
    # Use summary only — full pages are too large for one pass
    return page.summary


def ingest_wikipedia_topic(topic: str, driver):
    """
    Fetches a Wikipedia page and ingests it into the knowledge graph.
    """
    print(f"\n[WIKIPEDIA] Fetching: {topic}")
    text = fetch_wikipedia_page(topic)

    if not text:
        return

    print(f"  → {len(text)} characters fetched")
    ingest_document_text(
        text=text,
        source_name=f"wikipedia:{topic}",
        driver=driver
    )


if __name__ == "__main__":
    topics = [
        "OpenAI",
        "Sam Altman",
        "Elon Musk",
        "Greg Brockman",
    ]

    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

    for topic in topics:
        ingest_wikipedia_topic(topic, driver)

    print("\n[NORMALIZING] Cleaning up relationships...")
    normalize(driver)

    print("\n[CONTRADICTIONS] Scanning for conflicts...")
    detect_and_mark_contradictions(driver)

    driver.close()
    print("\n[COMPLETE] Wikipedia ingestion done.")

