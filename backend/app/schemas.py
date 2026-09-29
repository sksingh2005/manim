"""Pydantic schemas for the render API."""

from datetime import datetime

from pydantic import BaseModel, Field

from .config import LLMProvider, RenderQuality


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)
    provider: LLMProvider | None = None  # override default
    model: str | None = None  # override default, e.g. "claude-sonnet-4-5", "gemini-2.0-flash"
    quality: RenderQuality = RenderQuality.m
    scene_name: str = Field(default="GeneratedScene", pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    share_for_reuse: bool = False


class GenerateResponse(BaseModel):
    job_id: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str  # queued | running | succeeded | failed
    prompt: str
    provider: str
    model: str
    quality: str
    scene_name: str
    code: str | None = None
    log: str = ""
    error: str | None = None
    video_url: str | None = None
    share_for_reuse: bool = False
    reuse_indexed: bool = False
    reuse_error: str | None = None
    created_at: datetime
    updated_at: datetime


class SuggestionRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)
    quality: RenderQuality = RenderQuality.m


class VideoSuggestion(BaseModel):
    job_id: str
    prompt: str
    score: float
    video_url: str


class SuggestionResponse(BaseModel):
    suggestions: list[VideoSuggestion]
