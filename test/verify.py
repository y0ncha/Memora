#!/usr/bin/env python3
"""Quick verification script to test Interlock PoC is working."""

import sys
from pathlib import Path


def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...")
    try:
        from interlock.schemas.ticket import Ticket
        from interlock.fsm import State, transition
        from interlock.gates import IntakeGate, get_gate_for_state
        from interlock.storage import ArtifactStore
        print("  ✅ All imports successful")
        return True
    except ImportError as e:
        print(f"  ❌ Import failed: {e}")
        return False


def test_ticket_schema():
    """Test ticket schema validation."""
    print("\nTesting ticket schema...")
    try:
        from interlock.schemas.ticket import Ticket
        from pydantic import ValidationError
        from uuid import uuid4
        
        # Valid ticket
        ticket = Ticket(
            ticket_id="VERIFY-001",
            title="Verification Test",
            state="intake",
            run_id=str(uuid4()),
        )
        assert ticket.ticket_id == "VERIFY-001"
        print("  ✅ Valid ticket creation works")
        
        # Invalid ticket (empty ticket_id)
        try:
            invalid = Ticket(ticket_id="", title="Test", state="intake", run_id=str(uuid4()))
            print("  ❌ Validation should have failed")
            return False
        except ValidationError:
            print("  ✅ Invalid ticket correctly rejected")
        
        return True
    except Exception as e:
        print(f"  ❌ Ticket schema test failed: {e}")
        return False


def test_fsm():
    """Test FSM transitions."""
    print("\nTesting FSM transitions...")
    try:
        from interlock.fsm import State, transition
        
        # Test transition from intake
        result = transition(State.INTAKE)
        assert result.status == "pass"
        assert result.next_state == State.EXTRACT_REQUIREMENTS
        print(f"  ✅ Intake → {result.next_state.value} transition works")
        
        # Test terminal state
        result = transition(State.FINALIZE)
        assert result.status == "stop"
        print("  ✅ Finalize state correctly stops transitions")
        
        return True
    except Exception as e:
        print(f"  ❌ FSM test failed: {e}")
        return False


def test_gates():
    """Test validation gates."""
    print("\nTesting validation gates...")
    try:
        from interlock.schemas.ticket import Ticket
        from interlock.gates import IntakeGate, get_gate_for_state
        from uuid import uuid4
        
        # Valid ticket
        ticket = Ticket(
            ticket_id="VERIFY-002",
            title="Test",
            state="intake",
            run_id=str(uuid4()),
        )
        gate = IntakeGate()
        result = gate.validate(ticket)
        assert result.status == "pass"
        print("  ✅ IntakeGate passes valid ticket")
        
        # Wrong state
        ticket.state = "extract_requirements"
        result = gate.validate(ticket)
        assert result.status == "retry"
        print("  ✅ IntakeGate correctly rejects wrong state")
        
        # Get gate for state
        gate2 = get_gate_for_state("intake")
        assert isinstance(gate2, IntakeGate)
        print("  ✅ get_gate_for_state works")
        
        return True
    except Exception as e:
        print(f"  ❌ Gates test failed: {e}")
        return False


def test_storage():
    """Test artifact storage."""
    print("\nTesting artifact storage...")
    try:
        from interlock.schemas.ticket import Ticket
        from interlock.storage import ArtifactStore
        from uuid import uuid4
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(storage_dir=tmpdir)
            
            ticket = Ticket(
                ticket_id="VERIFY-003",
                title="Storage Test",
                state="intake",
                run_id=str(uuid4()),
            )
            
            store.save_ticket(ticket)
            store.save_event(
                run_id=ticket.run_id,
                event_type="test",
                state="intake",
                details={"test": True},
            )
            
            retrieved = store.get_ticket("VERIFY-003")
            assert retrieved is not None
            assert retrieved.ticket_id == "VERIFY-003"
            print("  ✅ Storage save and retrieve works")
        
        return True
    except Exception as e:
        print(f"  ❌ Storage test failed: {e}")
        return False


def test_end_to_end():
    """Test end-to-end workflow."""
    print("\nTesting end-to-end workflow...")
    try:
        from interlock.schemas.ticket import Ticket
        from interlock.fsm import State, transition
        from interlock.gates import get_gate_for_state
        from interlock.storage import ArtifactStore
        from uuid import uuid4
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(storage_dir=tmpdir)
            run_id = str(uuid4())
            
            # Step 1: Intake
            ticket1 = Ticket(
                ticket_id="E2E-001",
                title="E2E Test",
                state="intake",
                run_id=run_id,
            )
            
            gate1 = get_gate_for_state(ticket1.state)
            gate_result1 = gate1.validate(ticket1)
            assert gate_result1.status == "pass"
            
            transition_result1 = transition(State(ticket1.state))
            assert transition_result1.status == "pass"
            assert transition_result1.next_state == State.EXTRACT_REQUIREMENTS
            
            # Step 2: Extract requirements
            ticket2 = Ticket(
                ticket_id=ticket1.ticket_id,
                title=ticket1.title,
                state=transition_result1.next_state.value,
                run_id=run_id,
            )
            
            gate2 = get_gate_for_state(ticket2.state)
            gate_result2 = gate2.validate(ticket2)
            assert gate_result2.status == "pass"
            
            transition_result2 = transition(State(ticket2.state))
            assert transition_result2.status == "pass"
            assert transition_result2.next_state == State.SCOPE_CONTEXT
            
            store.save_ticket(ticket1)
            store.save_ticket(ticket2)
            
            print("  ✅ End-to-end workflow: intake → extract_requirements → scope_context")
        
        return True
    except Exception as e:
        print(f"  ❌ End-to-end test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all verification tests."""
    print("=" * 60)
    print("Interlock PoC Verification")
    print("=" * 60)
    
    tests = [
        ("Imports", test_imports),
        ("Ticket Schema", test_ticket_schema),
        ("FSM", test_fsm),
        ("Gates", test_gates),
        ("Storage", test_storage),
        ("End-to-End", test_end_to_end),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n  ❌ {name} test crashed: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("Verification Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Interlock PoC is working correctly.")
        print("\nNext steps:")
        print("  - Run the demo: python demo.py")
        print("  - Run unit tests: pytest test_interlock.py -v")
        print("  - See TESTING.md for more details")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please check the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
