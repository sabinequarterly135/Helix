"""PersonasSchema: YAML sidecar schema for persona storage.

Follows the same pattern as MocksSchema in registry/schemas.py:
- to_yaml() serializes to YAML string
- from_yaml() deserializes from YAML string with safe_load guard
"""

import yaml
from pydantic import BaseModel, Field

from api.synthesis.models import PersonaProfile


class PersonasSchema(BaseModel):
    """Schema for personas.yaml sidecar file.

    Contains persona profile definitions for adversarial conversation generation.
    Stored alongside other sidecar files in the prompt directory.

    Attributes:
        personas: List of persona profiles. Defaults to empty list.
    """

    personas: list[PersonaProfile] = Field(default_factory=list)

    def to_yaml(self) -> str:
        """Serialize to YAML string, excluding None fields."""
        data = self.model_dump(exclude_none=True)
        return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)

    @classmethod
    def from_yaml(cls, text: str) -> "PersonasSchema":
        """Deserialize from YAML string. Handles empty/None safely."""
        raw = yaml.safe_load(text) or {}
        return cls.model_validate(raw)
