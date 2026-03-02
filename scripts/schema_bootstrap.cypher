CREATE CONSTRAINT person_name_unique IF NOT EXISTS
FOR (p:Person) REQUIRE p.canonical_name IS UNIQUE;
CREATE CONSTRAINT org_name_unique IF NOT EXISTS
FOR (o:Organization) REQUIRE o.canonical_name IS UNIQUE;

CREATE CONSTRAINT loc_name_unique IF NOT EXISTS
FOR (l:Location) REQUIRE l.canonical_name IS UNIQUE;
CREATE CONSTRAINT concept_name_unique IF NOT EXISTS
FOR (c:Concept) REQUIRE c.canonical_name IS UNIQUE;

CREATE CONSTRAINT event_id_unique IF NOT EXISTS
FOR (e:Event) REQUIRE e.id IS UNIQUE;
CREATE CONSTRAINT doc_id_unique IF NOT EXISTS
FOR (d:Document) REQUIRE d.id IS UNIQUE;
CREATE CONSTRAINT chunk_id_unique IF NOT EXISTS
FOR (ch:Chunk) REQUIRE ch.id IS UNIQUE;

CREATE INDEX person_name_index IF NOT EXISTS
FOR (p:Person) ON (p.canonical_name);
CREATE INDEX org_name_index IF NOT EXISTS
FOR (o:Organization) ON (o.canonical_name);
CREATE INDEX chunk_doc_index IF NOT EXISTS
FOR (c:Chunk) ON (c.document_id);
