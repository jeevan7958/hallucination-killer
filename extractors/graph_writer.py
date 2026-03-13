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
            for person in result.persons:
                session.execute_write(self._merge_person, person)
            for org in result.organizations:
                session.execute_write(self._merge_org, org)
            for loc in result.locations:
                session.execute_write(self._merge_location, loc)
            for product in result.products:
                session.execute_write(self._merge_product, product)
            for concept in result.concepts:
                session.execute_write(self._merge_concept, concept)
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
    def _merge_product(tx, product):
        tx.run("""
            MERGE (p:Product {canonical_name: $name})
            SET p.category = $category,
                p.made_by = $made_by
        """, name=product.canonical_name,
             category=product.category,
             made_by=product.made_by)

    @staticmethod
    def _merge_concept(tx, concept):
        tx.run("""
            MERGE (c:Concept {canonical_name: $name})
            SET c.description = $description
        """, name=concept.canonical_name,
             description=concept.description)

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

