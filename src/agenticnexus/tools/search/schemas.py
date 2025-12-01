"""
Pydantic schemas for search tool responses.
"""
from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    """Individual search result."""

    url: str = Field(description="URL of the search result")
    title: str = Field(description="Title of the page")
    excerpt: str = Field(description="Relevant excerpt from the page")
    publish_date: str | None = Field(default=None, description="Publication date if available")


class SearchResponse(BaseModel):
    """Response from web search tool."""

    objective: str = Field(description="The search objective")
    search_queries: list[str] = Field(description="Queries that were executed")
    results: list[SearchResult] = Field(description="List of search results")
    total: int = Field(description="Total number of results returned")
