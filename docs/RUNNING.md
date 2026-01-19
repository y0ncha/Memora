# Running the Interlock MCP Server

## Quick Answer

**Yes, it's now a valid MCP server using FastMCP!** You can run it locally.

## Installation

1. **Install dependencies:**
   ```bash
   pip install -e .
   ```

   This installs:
   - `fastmcp` - The FastMCP library for building MCP servers
   - `pydantic` - For schema validation

## Running Locally

### Option 1: STDIO Mode (for MCP clients like Claude Desktop)

Run the server:
```bash
python -m interlock.server
```

The server will communicate via STDIN/STDOUT, which is the standard way MCP clients connect.

### Option 2: HTTP Mode (for testing with HTTP clients)

You can also run it as an HTTP server:
```python
# In interlock/server.py, change the last line to:
if __name__ == "__main__":
    mcp.run(transport="http", host="localhost", port=8000)
```

Then access it at `http://localhost:8000`

## Testing the Server

### Test with a Simple Client Script

Create `test_client.py`:

```python
import asyncio
import json
from interlock.schemas.ticket import Ticket
from uuid import uuid4

async def test_server():
    from fastmcp import Client
    
    # Connect to the server (in-memory for testing)
    from interlock.server import mcp
    client = Client(mcp)
    
    # Create a test ticket
    ticket = Ticket(
        ticket_id="TEST-001",
        title="Test ticket",
        state="intake",
        run_id=str(uuid4()),
    )
    
    # Call the tool
    result = await client.call_tool(
        "interlock_next_step",
        {"ticket_json": ticket.to_json()}
    )
    
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(test_server())
```

Run it:
```bash
python test_client.py
```

### Test with Claude Desktop (or other MCP client)

1. **Add to Claude Desktop MCP config** (`~/Library/Application Support/Claude/claude_desktop_config.json` on Mac):

```json
{
  "mcpServers": {
    "interlock": {
      "command": "py",
      "args": ["-m", "interlock.server"],
      "cwd": "/path/to/Interlock"
    }
  }
}
```

2. **Restart Claude Desktop**

3. **Use the tool** - Claude will be able to call `interlock_next_step` with ticket JSON.

## What Changed

- ✅ **Converted to FastMCP** - Much simpler API with decorators
- ✅ **Cleaner code** - No manual tool registration, FastMCP handles it
- ✅ **Same functionality** - All the governance logic remains the same
- ✅ **Easier to test** - FastMCP supports in-memory testing

## Server Features

The server provides one tool:

- **`interlock_next_step`**: 
  - Input: `ticket_json` (string) - JSON representation of a Ticket
  - Output: Governance response with:
    - `status`: "pass", "retry", or "stop"
    - `next_state`: Next FSM state (if status is "pass")
    - `agent_role`: What the agent should do in the next step
    - `gate_result`: Validation gate results

## Troubleshooting

### Import Errors
```bash
pip install -e .
```

### FastMCP Not Found
```bash
pip install fastmcp>=2.0.0
```

### Server Won't Start
- Check Python version: `python --version` (needs 3.11+)
- Check logs for errors
- Make sure you're in the project directory

## Next Steps

- The server is ready to use with any MCP-compatible client
- You can extend it by adding more tools using `@mcp.tool()` decorator
- For production, consider HTTP transport with authentication
