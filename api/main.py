import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from neo4j import GraphDatabase
from dotenv import load_dotenv

from extractors.entity_extractor import extract_entities
from extractors.graph_writer import GraphWriter
from scripts.ingest_documents import ingest_document_text, chunk_text
from scripts.normalize_relationships import normalize
from scripts.detect_contradictions import detect_and_mark_contradictions
from scripts.ingest_wikipedia import ingest_wikipedia_topic
from retrievers.qa_chain import answer_question

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

URI = os.getenv("NEO4J_URI")
USER = os.getenv("NEO4J_USER")
PASSWORD = os.getenv("NEO4J_PASSWORD")

app = FastAPI(
    title="Hallucination Killer API",
    description="GraphRAG system that eliminates LLM hallucinations using Neo4j knowledge graphs",
    version="1.0.0"
)

# Allow frontend to talk to this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_driver():
    return GraphDatabase.driver(URI, auth=(USER, PASSWORD))


# --- Request/Response Models ---

class TextIngestRequest(BaseModel):
    text: str
    source_name: str = "manual_input"

class WikipediaIngestRequest(BaseModel):
    topic: str

class QueryRequest(BaseModel):
    question: str

class IngestResponse(BaseModel):
    status: str
    source: str
    chunks_processed: int
    message: str

class QueryResponse(BaseModel):
    question: str
    answer: str
    status: str


# --- Routes ---

@app.get("/")
def root():
    return {
        "name": "Hallucination Killer API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": [
            "POST /ingest/text",
            "POST /ingest/wikipedia",
            "POST /query",
            "GET  /graph/stats",
            "GET  /graph/entities",
            "DELETE /graph/reset"
        ]
    }


@app.post("/ingest/text", response_model=IngestResponse)
def ingest_text(request: TextIngestRequest):
    """Ingest raw text into the knowledge graph."""
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    try:
        driver = get_driver()
        chunks = chunk_text(request.text)
        ingest_document_text(
            text=request.text,
            source_name=request.source_name,
            driver=driver
        )
        normalize(driver)
        detect_and_mark_contradictions(driver)
        driver.close()

        return IngestResponse(
            status="success",
            source=request.source_name,
            chunks_processed=len(chunks),
            message=f"Successfully ingested {len(chunks)} chunks into the knowledge graph"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest/wikipedia", response_model=IngestResponse)
def ingest_wikipedia(request: WikipediaIngestRequest):
    """Fetch a Wikipedia page and ingest it into the knowledge graph."""
    if not request.topic.strip():
        raise HTTPException(status_code=400, detail="Topic cannot be empty")

    try:
        driver = get_driver()
        ingest_wikipedia_topic(request.topic, driver)
        normalize(driver)
        detect_and_mark_contradictions(driver)
        driver.close()

        return IngestResponse(
            status="success",
            source=f"wikipedia:{request.topic}",
            chunks_processed=0,
            message=f"Successfully ingested Wikipedia page for '{request.topic}'"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest):
    """Ask a question and get a grounded answer from the knowledge graph."""
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    try:
        answer = answer_question(request.question)
        return QueryResponse(
            question=request.question,
            answer=answer,
            status="success"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/graph/stats")
def graph_stats():
    """Returns current knowledge graph statistics."""
    try:
        driver = get_driver()
        with driver.session() as session:
            node_counts = session.run("""
                MATCH (n)
                RETURN labels(n)[0] as type, count(n) as count
                ORDER BY count DESC
            """).data()

            rel_count = session.run("""
                MATCH ()-[r:RELATED]->()
                RETURN count(r) as count
            """).single()["count"]

            contradiction_count = session.run("""
                MATCH (c:ConflictMarker)
                RETURN count(c) as count
            """).single()["count"]

        driver.close()

        return {
            "status": "success",
            "nodes": node_counts,
            "total_relationships": rel_count,
            "total_contradictions": contradiction_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/graph/entities")
def graph_entities():
    """Returns all named entities in the knowledge graph."""
    try:
        driver = get_driver()
        with driver.session() as session:
            persons = session.run("""
                MATCH (p:Person)
                RETURN p.canonical_name as name, p.description as description
                ORDER BY p.canonical_name
            """).data()

            organizations = session.run("""
                MATCH (o:Organization)
                RETURN o.canonical_name as name, o.industry as industry
                ORDER BY o.canonical_name
            """).data()

            locations = session.run("""
                MATCH (l:Location)
                RETURN l.canonical_name as name
                ORDER BY l.canonical_name
            """).data()

        driver.close()

        return {
            "status": "success",
            "persons": persons,
            "organizations": organizations,
            "locations": locations
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/graph/reset")
def reset_graph():
    """
    Deletes all nodes and relationships.
    WARNING: This is irreversible. For development only.
    """
    try:
        driver = get_driver()
        with driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        driver.close()

        return {
            "status": "success",
            "message": "Graph cleared. All nodes and relationships deleted."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

