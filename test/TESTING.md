# Testing Interlock PoC

This document explains how to test the Interlock PoC implementation.

## Prerequisites

1. Python 3.11 or higher
2. Install dependencies:
   ```bash
   pip install -e .
   ```

   For development with tests:
   ```bash
   pip install -e ".[dev]"
   ```

## Quick Test: Run the Demo

The simplest way to verify everything works is to run the demo script:

```bash
python demo.py
```

**Expected Output:**
- You should see logs showing:
  - Ticket creation in "intake" state
  - Interlock responses with status, next_state, and agent_role
  - State transitions: intake → extract_requirements → scope_context
  - Validation failure demonstration
- Artifacts should be saved to `interlock_data/` directory:
  - `tickets.jsonl`: All ticket snapshots
  - `events.jsonl`: All events (tool calls, gates, transitions)

**Success Indicators:**
- ✅ No errors or exceptions
- ✅ Status is "pass" for valid tickets
- ✅ Next state transitions correctly
- ✅ Agent role descriptions are provided
- ✅ `interlock_data/` directory is created with files

## Unit Tests

Run the unit test suite:

```bash
# Run all tests
pytest test_interlock.py -v

# Run specific test class
pytest test_interlock.py::TestTicketSchema -v

# Run with coverage (if pytest-cov is installed)
pytest test_interlock.py --cov=interlock --cov-report=html
```

**Test Coverage:**
- ✅ Ticket schema validation (valid/invalid tickets)
- ✅ FSM state transitions
- ✅ Gate validation (IntakeGate, ExtractRequirementsGate)
- ✅ Artifact storage (save/retrieve tickets and events)
- ✅ End-to-end workflow

## Manual Testing: MCP Server

To test the MCP server directly, you'll need an MCP client. Here's a simple test script:

```python
# test_mcp_client.py
import asyncio
import json
from interlock.schemas.ticket import Ticket
from uuid import uuid4

async def test_mcp_tool():
    """Test the MCP tool by calling it directly."""
    from interlock.server import call_tool
    
    # Create a valid ticket
    ticket = Ticket(
        ticket_id="MCP-TEST-001",
        title="MCP Test Ticket",
        description="Testing MCP server",
        state="intake",
        run_id=str(uuid4()),
    )
    
    # Call the tool
    arguments = {"ticket_json": ticket.to_json()}
    result = await call_tool("interlock_next_step", arguments)
    
    # Parse response
    response = json.loads(result[0].text)
    print(json.dumps(response, indent=2))
    
    # Verify response structure
    assert "status" in response
    assert "next_state" in response
    assert "agent_role" in response
    assert "gate_result" in response
    
    print("\n✅ MCP tool test passed!")

if __name__ == "__main__":
    asyncio.run(test_mcp_tool())
```

Run it:
```bash
python test_mcp_client.py
```

## Verification Checklist

After running tests, verify:

### 1. Schema Validation Works
```python
from interlock.schemas.ticket import Ticket
from pydantic import ValidationError

# Should work
ticket = Ticket(ticket_id="TEST", title="Test", state="intake", run_id="run-1")

# Should fail
try:
    invalid = Ticket(ticket_id="", title="Test", state="intake", run_id="run-1")
except ValidationError:
    print("✅ Validation correctly rejects invalid tickets")
```

### 2. FSM Transitions Work
```python
from interlock.fsm import State, transition

result = transition(State.INTAKE)
assert result.status == "pass"
assert result.next_state == State.EXTRACT_REQUIREMENTS
print("✅ FSM transitions work correctly")
```

### 3. Gates Validate Correctly
```python
from interlock.gates import IntakeGate
from interlock.schemas.ticket import Ticket

ticket = Ticket(ticket_id="TEST", title="Test", state="intake", run_id="run-1")
gate = IntakeGate()
result = gate.validate(ticket)
assert result.status == "pass"
print("✅ Gates validate correctly")
```

### 4. Storage Persists Data
```python
from interlock.storage import ArtifactStore
from interlock.schemas.ticket import Ticket

store = ArtifactStore()
ticket = Ticket(ticket_id="STORAGE-TEST", title="Test", state="intake", run_id="run-1")
store.save_ticket(ticket)

retrieved = store.get_ticket("STORAGE-TEST")
assert retrieved is not None
assert retrieved.ticket_id == "STORAGE-TEST"
print("✅ Storage persists and retrieves tickets")
```

## Troubleshooting

### Import Errors
If you see `ModuleNotFoundError: No module named 'interlock'`:
- Make sure you've installed the package: `pip install -e .`
- Check you're in the project root directory

### MCP Library Issues
If MCP imports fail:
- Verify MCP is installed: `pip list | grep mcp`
- The MCP library API may have changed - check the [MCP documentation](https://modelcontextprotocol.io)

### Storage Directory Issues
If storage fails:
- Check write permissions in the project directory
- The `interlock_data/` directory will be created automatically

## Next Steps

Once all tests pass:
1. ✅ Verify the demo runs successfully
2. ✅ Check that artifacts are persisted correctly
3. ✅ Review the governance responses (status, next_state, agent_role)
4. ✅ Test with invalid tickets to verify validation works

For more details, see the [Planning Document](docs/Planing.md).
