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

with open("test_tool_output.txt", "w", encoding="utf-8") as f:
    for i, r in enumerate(result['results'], 1):
        f.write(f"--- Result {i} ---\n")
        f.write(f"Title: {r['title']}\n")
        f.write(f"URL: {r['url']}\n")
        f.write(f"Date: {r.get('publish_date', 'N/A')}\n")
        f.write(f"Excerpt: {r['excerpt'][:30000]}...\n\n")
