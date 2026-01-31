"""Pydantic models for source (alderman) data."""

from pydantic import BaseModel, ConfigDict, Field

from models.types import SourceID, WardNumber


class Source(BaseModel):
    """Represents a newsletter source (alderman or official)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: SourceID
    name: str = Field(..., min_length=1)
    ward_number: WardNumber | None = Field(None, ge=1, le=50)
    source_type: str = Field(..., min_length=1)
    newsletter_archive_url: str | None = None
    is_active: bool = True


class EmailSourceMapping(BaseModel):
    """Email pattern to source mapping."""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: int
    email_pattern: str = Field(..., min_length=1)
    source_id: SourceID
