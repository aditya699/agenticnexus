"""
AgenticNexus MCP Testing - Interactive CLI Chatbot with History
"""
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Colors for terminal
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# Conversation history
conversation_history = []

def print_header():
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*60}")
    print(f"  AgenticNexus MCP Chatbot")
    print(f"{'='*60}{Colors.END}\n")

def print_system_msg(msg):
    print(f"{Colors.YELLOW}[System] {msg}{Colors.END}")

def print_tool_event(msg):
    print(f"{Colors.BLUE}🔧 {msg}{Colors.END}")

def print_assistant_prefix():
    print(f"\n{Colors.GREEN}Assistant: {Colors.END}", end="", flush=True)

def chat_with_streaming(user_input):
    """Send message and stream response with conversation history"""
    
    print_system_msg("Processing your request...")
    
    # Build input array with history
    input_messages = []
    
    # Add conversation history as messages
    for msg in conversation_history:
        input_messages.append(msg)
    
    # Add current user message in proper format
    input_messages.append({
        "type": "message",
        "role": "user",
        "content": [
            {
                "type": "input_text",
                "text": user_input
            }
        ]
    })
    
    stream = client.responses.create(
        model="gpt-5",
        tools=[
            {
                "type": "mcp",
                "server_label": "agenticnexus",
                "server_description": "AgenticNexus MCP server with web search capability",
                "server_url": "https://c8d6c4a39bbf.ngrok-free.app/sse",
                "require_approval": "never"
            }
        ],
        input=input_messages,
        reasoning={"effort": "low"},
        text={"verbosity": "low"},
        stream=True,
        timeout=None
    )
    
    assistant_started = False
    assistant_response = ""
    response_id = None
    
    for event in stream:
        event_type = event.type
        
        # Capture response ID
        if event_type == "response.created":
            response_id = event.response.id
        
        # MCP Tool Discovery
        if event_type == "response.mcp_list_tools.in_progress":
            print_tool_event("Discovering available tools...")
            
        elif event_type == "response.mcp_list_tools.completed":
            print_tool_event("Tools loaded ✓")
        
        # MCP Tool Execution
        elif event_type == "response.mcp_call.in_progress":
            print_tool_event("Executing tool...")
            
        elif event_type == "response.mcp_call_arguments.done":
            print_tool_event(f"Calling with args: {event.arguments[:80]}...")
            
        elif event_type == "response.mcp_call.completed":
            print_tool_event("Tool execution complete ✓")
        
        # Assistant Response Text
        elif event_type == "response.output_text.delta":
            if not assistant_started:
                print_assistant_prefix()
                assistant_started = True
            print(event.delta, end="", flush=True)
            assistant_response += event.delta
            
        elif event_type == "response.output_text.done":
            print()  # New line after response
            
        # Completion
        elif event_type == "response.completed":
            usage = event.response.usage
            if usage:
                print(f"\n{Colors.CYAN}[Tokens: {usage.total_tokens} | History: {len(conversation_history)//2} exchanges]{Colors.END}")
        
        # Errors
        elif event_type == "error":
            print(f"\n{Colors.RED}[ERROR] {event.code}: {event.message}{Colors.END}")
            return
    
    # Add to conversation history in proper message format
    conversation_history.append({
        "type": "message",
        "role": "user",
        "content": [
            {
                "type": "input_text",
                "text": user_input
            }
        ]
    })
    
    conversation_history.append({
        "type": "message",
        "role": "assistant",
        "content": [
            {
                "type": "output_text",
                "text": assistant_response
            }
        ]
    })

def show_history():
    """Display conversation history"""
    if not conversation_history:
        print(f"{Colors.YELLOW}No conversation history yet.{Colors.END}\n")
        return
    
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*60}")
    print(f"  Conversation History ({len(conversation_history)//2} exchanges)")
    print(f"{'='*60}{Colors.END}\n")
    
    for msg in conversation_history:
        role = msg.get("role", "")
        content = msg.get("content", [])
        
        if role == "user":
            text = content[0].get("text", "")
            print(f"{Colors.BOLD}You: {Colors.END}{text[:150]}...")
        elif role == "assistant":
            text = content[0].get("text", "")
            print(f"{Colors.GREEN}Assistant: {Colors.END}{text[:150]}...")
        print()

def clear_history():
    """Clear conversation history"""
    global conversation_history
    conversation_history = []
    print(f"{Colors.YELLOW}Conversation history cleared.{Colors.END}\n")

def show_help():
    """Show available commands"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}Available Commands:{Colors.END}")
    print(f"  {Colors.BOLD}/history{Colors.END}  - Show conversation history")
    print(f"  {Colors.BOLD}/clear{Colors.END}    - Clear conversation history")
    print(f"  {Colors.BOLD}/help{Colors.END}     - Show this help message")
    print(f"  {Colors.BOLD}/exit{Colors.END}     - Exit the chatbot")
    print()

def main():
    print_header()
    print_system_msg("Connected to AgenticNexus MCP Server")
    print_system_msg("Type '/help' for commands or 'exit' to quit\n")
    
    while True:
        try:
            # Get user input
            user_input = input(f"{Colors.BOLD}You: {Colors.END}").strip()
            
            # Check for commands
            if user_input.lower() in ['exit', 'quit', 'q', '/exit']:
                print(f"\n{Colors.CYAN}Goodbye! 👋{Colors.END}\n")
                break
            
            elif user_input.lower() in ['/history', '/h']:
                show_history()
                continue
            
            elif user_input.lower() in ['/clear', '/c']:
                clear_history()
                continue
            
            elif user_input.lower() in ['/help', '/?']:
                show_help()
                continue
            
            # Skip empty inputs
            if not user_input:
                continue
            
            # Process the message
            chat_with_streaming(user_input)
            print()  # Extra line for spacing
            
        except KeyboardInterrupt:
            print(f"\n\n{Colors.CYAN}Goodbye! 👋{Colors.END}\n")
            break
        except Exception as e:
            print(f"\n{Colors.RED}[ERROR] {str(e)}{Colors.END}\n")

if __name__ == "__main__":
    main()