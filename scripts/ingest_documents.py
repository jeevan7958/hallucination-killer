import os
import uuid
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from neo4j import GraphDatabase
from dotenv import load_dotenv
from extractors.entity_extractor import extract_entities
from extractors.graph_writer import GraphWriter

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

URI = os.getenv("NEO4J_URI")
USER = os.getenv("NEO4J_USER")
PASSWORD = os.getenv("NEO4J_PASSWORD")

CHUNK_SIZE = 500  # characters per chunk

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    """
    Splits text into overlapping chunks.
    Overlap ensures relationships that span chunk boundaries are not lost.
    """
    words = text.split()
    chunks = []
    current_chunk = []
    current_size = 0

    for word in words:
        current_chunk.append(word)
        current_size += len(word) + 1
        if current_size >= chunk_size:
            chunks.append(" ".join(current_chunk))
            # Overlap: keep last 50 characters worth of words
            overlap_words = current_chunk[-10:]
            current_chunk = overlap_words
            current_size = sum(len(w) + 1 for w in overlap_words)

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks


def ingest_document(filepath: str, driver):
    """
    Reads a .txt file, chunks it, extracts entities from each chunk,
    writes everything to Neo4j with source tracking.
    """
    filename = os.path.basename(filepath)
    doc_id = str(uuid.uuid4())

    print(f"\n[INGESTING] {filename}")

    with open(filepath, 'r') as f:
        text = f.read()

    chunks = chunk_text(text)
    print(f"  → {len(chunks)} chunks created")

    # Write Document node to Neo4j
    with driver.session() as session:
        session.run("""
            MERGE (d:Document {id: $id})
            SET d.filename = $filename,
                d.chunk_count = $chunk_count
        """, id=doc_id, filename=filename, chunk_count=len(chunks))

    writer = GraphWriter()

    for i, chunk_text_content in enumerate(chunks):
        chunk_id = str(uuid.uuid4())

        # Write Chunk node linked to Document
        with driver.session() as session:
            session.run("""
                MERGE (c:Chunk {id: $chunk_id})
                SET c.text = $text,
                    c.document_id = $doc_id,
                    c.chunk_index = $index
                WITH c
                MATCH (d:Document {id: $doc_id})
                MERGE (d)-[:CONTAINS]->(c)
            """, chunk_id=chunk_id, text=chunk_text_content,
                 doc_id=doc_id, index=i)

        print(f"  → Processing chunk {i+1}/{len(chunks)}...")

        # Extract entities from this chunk
        try:
            result = extract_entities(chunk_text_content)

            # Write entities to graph
            writer.write(result)

            # Link extracted entities back to this chunk
            with driver.session() as session:
                for person in result.persons:
                    session.run("""
                        MATCH (c:Chunk {id: $chunk_id})
                        MATCH (p:Person {canonical_name: $name})
                        MERGE (c)-[:MENTIONS]->(p)
                    """, chunk_id=chunk_id, name=person.canonical_name)

                for org in result.organizations:
                    session.run("""
                        MATCH (c:Chunk {id: $chunk_id})
                        MATCH (o:Organization {canonical_name: $name})
                        MERGE (c)-[:MENTIONS]->(o)
                    """, chunk_id=chunk_id, name=org.canonical_name)

        except Exception as e:
            print(f"  [ERROR] Chunk {i+1} failed: {e}")
            continue

    writer.close()
    print(f"  [DONE] {filename} ingested successfully.")


def ingest_folder(folder_path: str):
    """
    Ingests all .txt files in a folder.
    """
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

    txt_files = [f for f in os.listdir(folder_path) if f.endswith('.txt')]

    if not txt_files:
        print(f"[WARNING] No .txt files found in {folder_path}")
        return

    print(f"[START] Found {len(txt_files)} documents to ingest")

    for filename in txt_files:
        filepath = os.path.join(folder_path, filename)
        ingest_document(filepath, driver)

    driver.close()
    print("\n[COMPLETE] All documents ingested.")


if __name__ == "__main__":
    ingest_folder(os.path.join(os.path.dirname(__file__), '..', 'data'))

