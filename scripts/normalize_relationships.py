import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

URI = os.getenv("NEO4J_URI")
USER = os.getenv("NEO4J_USER")
PASSWORD = os.getenv("NEO4J_PASSWORD")

# Normalization map — left side gets replaced by right side
RELATIONSHIP_NORMALIZATION = {
    "CO_FOUNDED":           "FOUNDED",
    "FIRED_AS_CEO":         "FIRED_FROM",
    "SERVES_AS_CEO":        "IS_CEO_OF",
    "WORKED_AS_CEO":        "IS_CEO_OF",
    "WORKED_AS_PRESIDENT":  "IS_PRESIDENT_OF",
    "RESIGNED_AS_PRESIDENT":"RESIGNED_FROM",
    "REINSTATED_AS_CEO":    "REINSTATED_AT",
}

def normalize(driver):
    with driver.session() as session:
        for old_type, new_type in RELATIONSHIP_NORMALIZATION.items():
            result = session.run("""
                MATCH (a)-[r:RELATED {type: $old_type}]->(b)
                SET r.type = $new_type
                RETURN count(r) as updated
            """, old_type=old_type, new_type=new_type)

            count = result.single()["updated"]
            if count > 0:
                print(f"  [{old_type}] → [{new_type}] : {count} relationships updated")

    print("[DONE] Normalization complete.")


if __name__ == "__main__":
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    print("[START] Normalizing relationships...")
    normalize(driver)
    driver.close()
