"""
Quick test to verify the search tool works.
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from dotenv import load_dotenv
load_dotenv()

from agenticnexus.tools.core.search.tool import web_search

# Test with specific question
result = web_search(
    objective="What happened in India today",
    search_queries=["India news today", "breaking news India"],
    max_results=3,
    max_chars_per_result=2000  # Get more content
)

print("✅ Tool executed!")
print(f"Found {result['total']} results\n")

for i, r in enumerate(result['results'], 1):
    print(f"--- Result {i} ---")
    print(f"Title: {r['title']}")
    print(f"URL: {r['url']}")
    print(f"Date: {r.get('publish_date', 'N/A')}")
    print(f"Excerpt: {r['excerpt'][:30000]}...")
    print()