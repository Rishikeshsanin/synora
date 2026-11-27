from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Tag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
class MusicSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    prompt: str = Field(min_length=1, max_length=2000)
    mode: Literal["instrumental", "vocals"]
    genres: list[Tag] = Field(max_length=12)
    moods: list[Tag] = Field(max_length=12)
    instruments: list[Tag] = Field(max_length=20)
    duration_seconds: int = Field(ge=15, le=120, strict=True)
    bpm: int | None = Field(default=None, ge=40, le=200, strict=True)
    lyrics: str | None = Field(default=None, max_length=6000)
    language: Tag | None = None

    @model_validator(mode="after")
    def check_lyrics(self):
        if self.mode == "instrumental" and self.lyrics:
            raise ValueError("instrumental jobs cannot include lyrics")
        return self

class ProjectSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)
