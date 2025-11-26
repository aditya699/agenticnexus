"""
Web search utility functions using Parallel API.
"""
import os
from parallel import AsyncParallel


async def search_web(
    objective: str,
    search_queries: list[str],
    max_results: int = 5,
    max_chars_per_result: int = 500
) -> dict:
    """Execute web search using Parallel API.

    Args:
        objective: High-level goal (e.g., "Latest news in India")
        search_queries: List of specific search queries
        max_results: Maximum number of results to return
        max_chars_per_result: Maximum characters per result excerpt

    Returns:
        Dictionary with search results or error information
    """
    api_key = os.getenv("PARALLEL_API_KEY")

    if not api_key:
        return {"error": "PARALLEL_API_KEY not configured", "results": []}

    try:
        client = AsyncParallel(api_key=api_key)
        search = await client.beta.search(
            objective=objective,
            search_queries=search_queries,
            max_results=max_results,
            max_chars_per_result=max_chars_per_result
        )

        results = []
        for result in search.results:
            results.append({
                "url": result.url,
                "title": result.title,
                "excerpt": result.excerpts[0] if result.excerpts else "",
                "publish_date": result.publish_date
            })

        return {
            "objective": objective,
            "search_queries": search_queries,
            "results": results,
            "total": len(results)
        }
    except Exception as e:
        return {"error": str(e), "results": []}
