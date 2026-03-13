import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from newsapi import NewsApiClient
from neo4j import GraphDatabase
from dotenv import load_dotenv
from scripts.ingest_documents import ingest_document_text
from scripts.normalize_relationships import normalize
from scripts.detect_contradictions import detect_and_mark_contradictions

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

URI = os.getenv("NEO4J_URI")
USER = os.getenv("NEO4J_USER")
PASSWORD = os.getenv("NEO4J_PASSWORD")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")


def ingest_news_topic(topic: str, driver, max_articles: int = 5):
    """
    Fetches recent news articles about a topic
    and ingests them into the knowledge graph.
    """
    print(f"\n[NEWS] Fetching articles about: {topic}")

    newsapi = NewsApiClient(api_key=NEWS_API_KEY)

    response = newsapi.get_everything(
        q=topic,
        language='en',
        sort_by='relevancy',
        page_size=max_articles
    )

    articles = response.get('articles', [])
    print(f"  → {len(articles)} articles found")

    for i, article in enumerate(articles):
        # Combine title + description + content for richer extraction
        text_parts = [
            article.get('title', ''),
            article.get('description', ''),
            article.get('content', '')
        ]
        text = " ".join([p for p in text_parts if p])

        if not text.strip():
            continue

        source_name = f"news:{article.get('source', {}).get('name', 'unknown')}:{i}"
        print(f"\n  [ARTICLE {i+1}] {article.get('title', '')[:60]}...")

        ingest_document_text(
            text=text,
            source_name=source_name,
            driver=driver
        )


if __name__ == "__main__":
    topics = [
        "OpenAI Sam Altman",
        "Elon Musk artificial intelligence",
    ]

    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

    for topic in topics:
        ingest_news_topic(topic, driver)

    print("\n[NORMALIZING] Cleaning up relationships...")
    normalize(driver)

    print("\n[CONTRADICTIONS] Scanning for conflicts...")
    detect_and_mark_contradictions(driver)

    driver.close()
    print("\n[COMPLETE] News ingestion done.")
