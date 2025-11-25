"""
Test AgenticNexus MCP server via OpenAI Responses API.
"""
import os
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

response = client.responses.create(
    model="gpt-5",
    tools=[
        {
            "type": "mcp",
            "server_label": "agenticnexus",
            "server_description": "AgenticNexus MCP server with web search capability",
            "server_url": "https://1dfb33212f85.ngrok-free.app/sse",
            "require_approval": "never"
        }
    ],
    input="Search for latest news about artificial intelligence"
)

print("=== OpenAI Response ===")
print(response.output_text)
print("\n=== Full Response ===")
print(response)