"""
Web search tool using Parallel API.
"""
import os
from parallel import Parallel
from agenticnexus.tools.base import tool


@tool(
    name="web_search",
    description="Search the web for information using multiple search queries to achieve an objective."
)
def web_search(
    objective: str,
    search_queries: list,
    max_results: int = 5,
    max_chars_per_result: int = 500
) -> dict:
    """
    Search the web using Parallel API.
    
    Args:
        objective: High-level goal (e.g., "Latest news in India")
        search_queries: List of specific search queries (e.g., ["India news", "India today"])
        max_results: Maximum number of results to return (default: 5)
        max_chars_per_result: Maximum characters per result excerpt (default: 500)
        
    Returns:
        Dictionary with search results
    """
    api_key = os.getenv("PARALLEL_API_KEY")
    
    if not api_key:
        return {
            "error": "PARALLEL_API_KEY not configured",
            "results": []
        }
    
    try:
        client = Parallel(api_key=api_key)
        
        search = client.beta.search(
            objective=objective,
            search_queries=search_queries,
            max_results=max_results,
            max_chars_per_result=max_chars_per_result
        )
        
        # Extract results
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
        return {
            "error": str(e),
            "results": []
        }