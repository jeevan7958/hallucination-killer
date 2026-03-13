import os
import sys
import time
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from neo4j import GraphDatabase
from dotenv import load_dotenv
from groq import Groq
from collections import defaultdict

from config.logger import get_logger
from extractors.graph_writer import GraphWriter
from scripts.ingest_documents import ingest_document_text, chunk_text
from scripts.normalize_relationships import normalize
from scripts.detect_contradictions import detect_and_mark_contradictions
from scripts.ingest_wikipedia import ingest_wikipedia_topic, fetch_wikipedia_page
from retrievers.qa_chain import answer_question

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

URI = os.getenv("NEO4J_URI")
USER = os.getenv("NEO4J_USER")
PASSWORD = os.getenv("NEO4J_PASSWORD")

logger = get_logger("api")

app = FastAPI(
    title="Hallucination Killer API",
    description="GraphRAG system that eliminates LLM hallucinations using Neo4j knowledge graphs",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Rate Limiting ---
# Simple in-memory rate limiter
# Tracks request counts per IP address
request_counts = defaultdict(list)
RATE_LIMIT = 20       # max requests
RATE_WINDOW = 60      # per 60 seconds

def check_rate_limit(ip: str):
    now = time.time()
    # Keep only requests within the time window
    request_counts[ip] = [t for t in request_counts[ip] if now - t < RATE_WINDOW]
    if len(request_counts[ip]) >= RATE_LIMIT:
        logger.warning(f"Rate limit exceeded for IP: {ip}")
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests. Maximum {RATE_LIMIT} requests per {RATE_WINDOW} seconds."
        )
    request_counts[ip].append(now)


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
            "GET  /health",
            "DELETE /graph/reset"
        ]
    }


@app.get("/health")
def health_check():
    """
    Checks if Neo4j and Groq are both reachable.
    Returns status of each service independently.
    """
    health = {
        "status": "healthy",
        "services": {
            "neo4j": "unknown",
            "groq": "unknown"
        }
    }

    # Check Neo4j
    try:
        driver = get_driver()
        with driver.session() as session:
            session.run("RETURN 1")
        driver.close()
        health["services"]["neo4j"] = "healthy"
        logger.info("Health check: Neo4j is healthy")
    except Exception as e:
        health["services"]["neo4j"] = f"unhealthy: {str(e)}"
        health["status"] = "degraded"
        logger.error(f"Health check: Neo4j is unhealthy: {e}")

    # Check Groq
    try:
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1
        )
        health["services"]["groq"] = "healthy"
        logger.info("Health check: Groq is healthy")
    except Exception as e:
        health["services"]["groq"] = f"unhealthy: {str(e)}"
        health["status"] = "degraded"
        logger.error(f"Health check: Groq is unhealthy: {e}")

    return health


@app.post("/ingest/text", response_model=IngestResponse)
def ingest_text(request: TextIngestRequest, req: Request):
    check_rate_limit(req.client.host)

    # Input validation
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    if len(request.text.strip()) < 20:
        raise HTTPException(status_code=400, detail="Text is too short to extract meaningful entities. Please provide at least a sentence.")

    if len(request.text) > 50000:
        raise HTTPException(status_code=400, detail="Text is too long. Please keep it under 50,000 characters.")

    logger.info(f"Ingesting text | source: {request.source_name} | length: {len(request.text)}")

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

        logger.info(f"Text ingestion complete | source: {request.source_name} | chunks: {len(chunks)}")

        return IngestResponse(
            status="success",
            source=request.source_name,
            chunks_processed=len(chunks),
            message=f"Successfully ingested {len(chunks)} chunks into the knowledge graph."
        )
    except Exception as e:
        logger.error(f"Text ingestion failed | source: {request.source_name} | error: {e}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@app.post("/ingest/wikipedia", response_model=IngestResponse)
def ingest_wikipedia(request: WikipediaIngestRequest, req: Request):
    check_rate_limit(req.client.host)

    if not request.topic.strip():
        raise HTTPException(status_code=400, detail="Topic cannot be empty.")

    # Wikipedia existence check
    page_text = fetch_wikipedia_page(request.topic)
    if not page_text:
        logger.warning(f"Wikipedia page not found: {request.topic}")
        raise HTTPException(
            status_code=404,
            detail=f"No Wikipedia page found for '{request.topic}'. Check the spelling or try a different topic."
        )

    logger.info(f"Ingesting Wikipedia topic: {request.topic}")

    try:
        driver = get_driver()
        ingest_wikipedia_topic(request.topic, driver)
        normalize(driver)
        detect_and_mark_contradictions(driver)
        driver.close()

        logger.info(f"Wikipedia ingestion complete: {request.topic}")

        return IngestResponse(
            status="success",
            source=f"wikipedia:{request.topic}",
            chunks_processed=0,
            message=f"Successfully ingested Wikipedia page for '{request.topic}'."
        )
    except Exception as e:
        logger.error(f"Wikipedia ingestion failed | topic: {request.topic} | error: {e}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest, req: Request):
    check_rate_limit(req.client.host)

    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    if len(request.question.strip()) < 5:
        raise HTTPException(status_code=400, detail="Question is too short. Please ask a complete question.")

    logger.info(f"Query received: {request.question}")

    try:
        answer = answer_question(request.question)

        # Fallback response if graph has no data
        if "does not contain enough information" in answer.lower():
            answer += "\n\nSuggestion: Try ingesting a relevant Wikipedia page or text first using the Ingest panels, then ask your question again."

        logger.info(f"Query answered: {request.question}")

        return QueryResponse(
            question=request.question,
            answer=answer,
            status="success"
        )
    except Exception as e:
        logger.error(f"Query failed | question: {request.question} | error: {e}")
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


@app.get("/graph/stats")
def graph_stats(req: Request):
    check_rate_limit(req.client.host)
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
        logger.error(f"Graph stats failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/graph/entities")
def graph_entities(req: Request):
    check_rate_limit(req.client.host)
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

            products = session.run("""
                MATCH (p:Product)
                RETURN p.canonical_name as name, p.category as category
                ORDER BY p.canonical_name
            """).data()

        driver.close()

        return {
            "status": "success",
            "persons": persons,
            "organizations": organizations,
            "locations": locations,
            "products": products
        }
    except Exception as e:
        logger.error(f"Graph entities failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/graph/reset")
def reset_graph(req: Request):
    check_rate_limit(req.client.host)
    try:
        driver = get_driver()
        with driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        driver.close()
        logger.warning("Graph reset — all nodes and relationships deleted")
        return {
            "status": "success",
            "message": "Graph cleared. All nodes and relationships deleted."
        }
    except Exception as e:
        logger.error(f"Graph reset failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- Serve Frontend ---
app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/ui")
def serve_ui():
    return FileResponse("frontend/index.html")

