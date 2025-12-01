"""
Web search utility functions using Parallel API.
"""
import os

from parallel import AsyncParallel

from .schemas import SearchResponse, SearchResult


async def search_web(
    objective: str,
    search_queries: list[str],
    max_results: int = 5,
    max_chars_per_result: int = 500
) -> SearchResponse:
    """Execute web search using Parallel API.

    Args:
        objective: High-level goal (e.g., "Latest news in India")
        search_queries: List of specific search queries
        max_results: Maximum number of results to return
        max_chars_per_result: Maximum characters per result excerpt

    Returns:
        SearchResponse with results

    Raises:
        ValueError: If PARALLEL_API_KEY is not configured
    """
    api_key = os.getenv("PARALLEL_API_KEY")

    if not api_key:
        raise ValueError("PARALLEL_API_KEY not configured")

    client = AsyncParallel(api_key=api_key)
    search = await client.beta.search(
        objective=objective,
        search_queries=search_queries,
        max_results=max_results,
        max_chars_per_result=max_chars_per_result
    )

    results = [
        SearchResult(
            url=result.url,
            title=result.title,
            excerpt=result.excerpts[0] if result.excerpts else "",
            publish_date=result.publish_date
        )
        for result in search.results
    ]

    return SearchResponse(
        objective=objective,
        search_queries=search_queries,
        results=results,
        total=len(results)
    )
