"""
Author: Aditya Bhatt
Hybrid MCP Client - Responses API + Direct MCP Control

Architecture:
- OpenAI Responses API (GPT-5) for LLM decisions
- Direct MCP connection for tool execution + REAL-TIME progress visibility
- NO built-in MCP from OpenAI (we control everything)

PROVEN: Progress notifications stream in real-time from server!
"""
import asyncio
import json
import os
from openai import OpenAI
from mcp import ClientSession
from mcp.client.sse import sse_client
from dotenv import load_dotenv

load_dotenv()

# Initialize clients
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Conversation history
conversation_history = []

# =============================================================================
# UI/UX: Colors and Formatting
# =============================================================================

class Colors:
    """ANSI escape codes for terminal colors."""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    MAGENTA = '\033[35m'
    WHITE = '\033[97m'
    GRAY = '\033[90m'
    END = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    UNDERLINE = '\033[4m'


def print_banner():
    """Print the startup banner."""
    print(f"\n{Colors.CYAN}{Colors.BOLD}")
    print("  ╔═══════════════════════════════════════════════════════════╗")
    print("  ║                                                           ║")
    print("  ║   ▄▀█ █▀▀ █▀▀ █▄░█ ▀█▀ █ █▀▀   █▄░█ █▀▀ ▀▄▀ █░█ █▀      ║")
    print("  ║   █▀█ █▄█ ██▄ █░▀█ ░█░ █ █▄▄   █░▀█ ██▄ █░█ █▄█ ▄█      ║")
    print("  ║                                                           ║")
    print("  ║           Hybrid MCP Client - GPT-5 + Direct MCP          ║")
    print("  ╚═══════════════════════════════════════════════════════════╝")
    print(f"{Colors.END}")


def print_divider(char="─", width=60):
    """Print a divider line."""
    print(f"{Colors.GRAY}{char * width}{Colors.END}")


def print_status(msg: str):
    """Print a status message in yellow."""
    print(f"{Colors.YELLOW}  ● {msg}{Colors.END}")


def print_success(msg: str):
    """Print a success message in green."""
    print(f"{Colors.GREEN}  ✓ {msg}{Colors.END}")


def print_error(msg: str):
    """Print an error message in red."""
    print(f"{Colors.RED}  ✗ {msg}{Colors.END}")


def print_tool_event(msg: str):
    """Print a tool-related message in blue."""
    print(f"{Colors.BLUE}  ⚡ {msg}{Colors.END}")


def print_assistant_prefix():
    """Print the assistant response prefix."""
    print(f"\n{Colors.GREEN}{Colors.BOLD}  Assistant:{Colors.END} ", end="", flush=True)


def print_user_prompt():
    """Print the user input prompt."""
    return input(f"\n{Colors.BOLD}  You:{Colors.END} ").strip()


def format_progress_bar(progress: float, total: float, message: str | None = None) -> str:
    """Format a colored progress bar."""
    percentage = int((progress / total) * 100)
    bar_length = 25
    filled = int(bar_length * progress / total)

    # Color gradient based on progress
    if percentage < 33:
        bar_color = Colors.RED
    elif percentage < 66:
        bar_color = Colors.YELLOW
    else:
        bar_color = Colors.GREEN

    bar = f"{bar_color}{'█' * filled}{Colors.GRAY}{'░' * (bar_length - filled)}{Colors.END}"
    status_msg = f" {Colors.DIM}{message}{Colors.END}" if message else ""

    return f"  {Colors.CYAN}Progress:{Colors.END} [{bar}] {percentage:3d}%{status_msg}"


# =============================================================================
# Commands
# =============================================================================

def show_help():
    """Display available commands."""
    print(f"\n{Colors.CYAN}{Colors.BOLD}  Available Commands:{Colors.END}")
    print_divider()
    print(f"  {Colors.BOLD}/help{Colors.END}     {Colors.GRAY}or{Colors.END} {Colors.BOLD}/?{Colors.END}      Show this help message")
    print(f"  {Colors.BOLD}/history{Colors.END}  {Colors.GRAY}or{Colors.END} {Colors.BOLD}/h{Colors.END}      Show conversation history")
    print(f"  {Colors.BOLD}/clear{Colors.END}    {Colors.GRAY}or{Colors.END} {Colors.BOLD}/c{Colors.END}      Clear conversation history")
    print(f"  {Colors.BOLD}/tools{Colors.END}    {Colors.GRAY}or{Colors.END} {Colors.BOLD}/t{Colors.END}      Show loaded MCP tools")
    print(f"  {Colors.BOLD}exit{Colors.END}      {Colors.GRAY}or{Colors.END} {Colors.BOLD}quit{Colors.END}    Exit the chatbot")
    print_divider()
    print()


def show_history():
    """Display conversation history."""
    if not conversation_history:
        print_status("No conversation history yet.")
        return

    print(f"\n{Colors.CYAN}{Colors.BOLD}  Conversation History ({len(conversation_history)} exchanges):{Colors.END}")
    print_divider()

    for i, exchange in enumerate(conversation_history, 1):
        user_msg = exchange.get("user", "")[:100]
        assistant_msg = exchange.get("assistant", "")[:100]

        print(f"  {Colors.GRAY}[{i}]{Colors.END}")
        print(f"  {Colors.BOLD}You:{Colors.END} {user_msg}{'...' if len(exchange.get('user', '')) > 100 else ''}")
        print(f"  {Colors.GREEN}Assistant:{Colors.END} {assistant_msg}{'...' if len(exchange.get('assistant', '')) > 100 else ''}")
        print()

    print_divider()


def clear_history():
    """Clear conversation history."""
    global conversation_history
    conversation_history = []
    print_success("Conversation history cleared.")


def show_tools(tools: list):
    """Display loaded MCP tools."""
    print(f"\n{Colors.CYAN}{Colors.BOLD}  Loaded MCP Tools ({len(tools)}):{Colors.END}")
    print_divider()

    for tool in tools:
        print(f"  {Colors.BLUE}●{Colors.END} {Colors.BOLD}{tool.name}{Colors.END}")
        if tool.description:
            desc = tool.description[:80]
            print(f"    {Colors.GRAY}{desc}{'...' if len(tool.description) > 80 else ''}{Colors.END}")

    print_divider()
    print()


def mcp_to_openai_tool(tool):
    """Convert MCP tool to OpenAI Responses API format."""
    return {
        "type": "function",
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.inputSchema
    }


async def process_query(query: str, session: ClientSession, openai_tools: list):
    """Process query using Responses API + direct MCP tool execution."""
    print_status("Processing your request...")

    # Call OpenAI RESPONSES API with GPT-5 (NO server_url - we control tools!)
    try:
        stream = openai_client.responses.create(
            model="gpt-5",
            tools=openai_tools,
            input=[
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": query}]
                }
            ],
            reasoning={"effort": "low"},
            text={"verbosity": "low"},
            stream=True,
            timeout=None
        )
    except Exception as e:
        print_error(f"OpenAI API Error: {e}")
        return ""

    tool_calls_detected = []
    assistant_response = ""
    current_tool_name = None
    assistant_started = False

    # Stream events from GPT-5
    for event in stream:
        event_type = event.type

        # Capture tool name from output_item.added
        if event_type == "response.output_item.added":
            if hasattr(event, 'item') and hasattr(event.item, 'name'):
                current_tool_name = event.item.name
                if current_tool_name:
                    print_tool_event(f"GPT-5 requesting tool: {Colors.BOLD}{current_tool_name}{Colors.END}")

        # Function call completed - capture arguments
        elif event_type == "response.function_call_arguments.done":
            tool_calls_detected.append({
                "name": current_tool_name or "unknown",
                "arguments": event.arguments
            })

        # Assistant text streaming
        elif event_type == "response.output_text.delta":
            if not assistant_started:
                print_assistant_prefix()
                assistant_started = True
            print(event.delta, end="", flush=True)
            assistant_response += event.delta

    # If tools were called, execute them with REAL-TIME progress
    if tool_calls_detected:
        print(f"\n\n{Colors.CYAN}  ╭{'─' * 56}╮{Colors.END}")
        print(f"{Colors.CYAN}  │{Colors.END}  {Colors.BOLD}Tool Execution{Colors.END} - {len(tool_calls_detected)} tool(s) to run{' ' * 23}{Colors.CYAN}│{Colors.END}")
        print(f"{Colors.CYAN}  ╰{'─' * 56}╯{Colors.END}\n")

        all_tool_results = []

        for idx, tool_call in enumerate(tool_calls_detected, 1):
            tool_name = tool_call["name"]
            tool_args = json.loads(tool_call["arguments"])

            print(f"  {Colors.BLUE}[{idx}/{len(tool_calls_detected)}]{Colors.END} {Colors.BOLD}{tool_name}{Colors.END}")

            # Format arguments nicely
            args_str = json.dumps(tool_args, indent=2)
            for line in args_str.split('\n'):
                print(f"      {Colors.GRAY}{line}{Colors.END}")
            print()

            # Progress callback with visual progress bar
            async def progress_handler(progress: float, total: float | None, message: str | None):
                """Handle REAL-TIME progress notifications from MCP server."""
                if total and total > 0:
                    progress_line = format_progress_bar(progress, total, message)
                    # Clear line and print progress
                    print(f"\r{' ' * 80}\r{progress_line}", end="", flush=True)
                elif message:
                    print(f"\r{' ' * 80}\r  {Colors.CYAN}Progress:{Colors.END} {message}", end="", flush=True)

            # Execute via OUR MCP connection with STREAMING progress!
            result = await session.call_tool(
                tool_name,
                tool_args,
                meta={"progressToken": f"progress-tool-{idx}"},
                progress_callback=progress_handler  # REAL-TIME UPDATES!
            )
            print(f"\r{' ' * 80}\r", end="")  # Clear progress line
            print_success(f"Tool complete: {tool_name}")
            print()

            # Extract result
            result_text = ""
            if result.content:
                if hasattr(result.content[0], 'text'):
                    result_text = result.content[0].text
                else:
                    result_text = str(result.content[0])

            all_tool_results.append({
                "tool": tool_name,
                "result": result_text
            })

        # Send all results back to GPT-5 for final answer
        print_divider()
        print_status("Synthesizing final response...")

        # Build conversation with tool results
        conversation = [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": query}]
            }
        ]

        # Add tool execution context
        tool_summary = "\n\n".join([
            f"Tool: {tr['tool']}\nResult: {tr['result']}"
            for tr in all_tool_results
        ])

        conversation.append({
            "type": "message",
            "role": "user",
            "content": [{
                "type": "input_text",
                "text": f"Here are the tool execution results:\n\n{tool_summary}\n\nPlease provide a comprehensive answer based on these results."
            }]
        })

        # Get final answer from GPT-5
        final_stream = openai_client.responses.create(
            model="gpt-5",
            input=conversation,
            reasoning={"effort": "low"},
            text={"verbosity": "low"},
            stream=True
        )

        print_assistant_prefix()
        final_response = ""
        for event in final_stream:
            if event.type == "response.output_text.delta":
                print(event.delta, end="", flush=True)
                final_response += event.delta
        print("\n")
        assistant_response = final_response

    else:
        # No tools called, just text response
        if assistant_response:
            print("\n")

    # Store in conversation history
    if assistant_response:
        conversation_history.append({
            "user": query,
            "assistant": assistant_response
        })

    return assistant_response


async def main():
    """Main hybrid client - connects to MCP server directly."""
    server_url = "http://localhost:8002/sse"

    # Display banner
    print_banner()

    print_status("Connecting to AgenticNexus MCP server...")

    try:
        async with sse_client(server_url) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                # Initialize connection
                await session.initialize()
                print_success("Connected to MCP server!")

                # Get tools from OUR server
                tools_response = await session.list_tools()
                tools = tools_response.tools
                print_success(f"Loaded {len(tools)} tools: {Colors.CYAN}{', '.join([t.name for t in tools])}{Colors.END}")

                # Convert to OpenAI format
                openai_tools = [mcp_to_openai_tool(t) for t in tools]

                print()
                print_divider()
                print(f"  {Colors.GRAY}Type {Colors.BOLD}/help{Colors.END}{Colors.GRAY} for commands or start chatting{Colors.END}")
                print_divider()

                # Interactive loop
                while True:
                    try:
                        user_input = print_user_prompt()

                        # Handle commands
                        if user_input.lower() in ['quit', 'exit', 'q', '/exit']:
                            print(f"\n{Colors.CYAN}  Goodbye! 👋{Colors.END}\n")
                            break

                        elif user_input.lower() in ['/help', '/?']:
                            show_help()
                            continue

                        elif user_input.lower() in ['/history', '/h']:
                            show_history()
                            continue

                        elif user_input.lower() in ['/clear', '/c']:
                            clear_history()
                            continue

                        elif user_input.lower() in ['/tools', '/t']:
                            show_tools(tools)
                            continue

                        # Skip empty inputs
                        if not user_input:
                            continue

                        # Process the query
                        await process_query(user_input, session, openai_tools)

                    except KeyboardInterrupt:
                        print(f"\n\n{Colors.CYAN}  Goodbye! 👋{Colors.END}\n")
                        break

    except ConnectionRefusedError:
        print_error("Could not connect to MCP server at " + server_url)
        print(f"  {Colors.GRAY}Make sure the server is running: python -m agenticnexus.mcp_server{Colors.END}")
    except Exception as e:
        print_error(f"Connection error: {e}")


if __name__ == "__main__":
    asyncio.run(main())