import os
from neo4j import GraphDatabase
from dotenv import load_dotenv
from extractors.schema import ExtractionResult

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

URI = os.getenv("NEO4J_URI")
USER = os.getenv("NEO4J_USER")
PASSWORD = os.getenv("NEO4J_PASSWORD")

class GraphWriter:
    def __init__(self):
        self.driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

    def close(self):
        self.driver.close()

    def write(self, result: ExtractionResult):
        with self.driver.session() as session:
            # Write Persons
            for person in result.persons:
                session.execute_write(self._merge_person, person)

            # Write Organizations
            for org in result.organizations:
                session.execute_write(self._merge_org, org)

            # Write Locations
            for loc in result.locations:
                session.execute_write(self._merge_location, loc)

            # Write Relationships
            for rel in result.relationships:
                session.execute_write(self._merge_relationship, rel)

        print("[OK] Graph write complete.")

    @staticmethod
    def _merge_person(tx, person):
        tx.run("""
            MERGE (p:Person {canonical_name: $name})
            SET p.description = $description,
                p.aliases = $aliases
        """, name=person.canonical_name,
             description=person.description,
             aliases=person.aliases)

    @staticmethod
    def _merge_org(tx, org):
        tx.run("""
            MERGE (o:Organization {canonical_name: $name})
            SET o.industry = $industry,
                o.aliases = $aliases
        """, name=org.canonical_name,
             industry=org.industry,
             aliases=org.aliases)

    @staticmethod
    def _merge_location(tx, loc):
        tx.run("""
            MERGE (l:Location {canonical_name: $name})
        """, name=loc.canonical_name)

    @staticmethod
    def _merge_relationship(tx, rel):
        tx.run("""
            MATCH (source {canonical_name: $source})
            MATCH (target {canonical_name: $target})
            MERGE (source)-[r:RELATED {type: $type}]->(target)
            SET r.year = $year,
                r.end_year = $end_year,
                r.notes = $notes
        """, source=rel.source,
             target=rel.target,
             type=rel.type,
             year=rel.year,
             end_year=rel.end_year,
             notes=rel.notes)


if __name__ == "__main__":
    from extractors.entity_extractor import extract_entities

    test_text = """
    Elon Musk co-founded OpenAI in 2015 alongside Sam Altman and Greg Brockman.
    The organization is headquartered in San Francisco, California.
    Musk later resigned from the OpenAI board in 2018.
    Sam Altman currently serves as CEO of OpenAI.
    """

    print("[1] Extracting entities...")
    result = extract_entities(test_text)

    print("[2] Writing to Neo4j...")
    writer = GraphWriter()
    writer.write(result)
    writer.close()

    print("[3] Verifying — querying Neo4j...")
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    with driver.session() as session:
        persons = session.run("MATCH (p:Person) RETURN p.canonical_name").data()
        rels = session.run("MATCH (a)-[r:RELATED]->(b) RETURN a.canonical_name, r.type, b.canonical_name").data()

    print("\n--- PERSONS IN NEO4J ---")
    for p in persons:
        print(f"  {p['p.canonical_name']}")

    print("\n--- RELATIONSHIPS IN NEO4J ---")
    for r in rels:
        print(f"  ({r['a.canonical_name']}) --[{r['r.type']}]--> ({r['b.canonical_name']})")

    driver.close()

