from pydantic import BaseModel, Field
from typing import List, Optional

class Person(BaseModel):
    canonical_name: str = Field(description="Full, proper name. e.g. 'Elon Musk' not 'Musk'")
    aliases: List[str] = Field(default=[], description="Other names this person is referred to")
    description: Optional[str] = Field(default=None, description="One line about who this person is")

class Organization(BaseModel):
    canonical_name: str = Field(description="Full, proper name. e.g. 'Tesla Inc' not 'tesla'")
    aliases: List[str] = Field(default=[], description="Other names this org is referred to")
    industry: Optional[str] = Field(default=None, description="e.g. 'Electric Vehicles'")

class Location(BaseModel):
    canonical_name: str = Field(description="Full location name. e.g. 'San Francisco, California'")

class Relationship(BaseModel):
    source: str = Field(description="The entity where the relationship starts")
    target: str = Field(description="The entity where the relationship ends")
    type: str = Field(description="Relationship type in UPPER_SNAKE_CASE. e.g. FOUNDED, WORKS_FOR, LOCATED_IN")
    year: Optional[int] = Field(default=None, description="Year this relationship started")
    end_year: Optional[int] = Field(default=None, description="Year this relationship ended, if applicable")
    notes: Optional[str] = Field(default=None, description="Any extra context about this relationship")

class ExtractionResult(BaseModel):
    persons: List[Person] = Field(default=[])
    organizations: List[Organization] = Field(default=[])
    locations: List[Location] = Field(default=[])
    relationships: List[Relationship] = Field(default=[])
