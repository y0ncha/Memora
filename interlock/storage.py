"""Artifact persistence for Interlock."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from interlock.schemas.ticket import Ticket

logger = logging.getLogger(__name__)


class ArtifactStore:
    """Store for persisting tickets and events."""
    
    def __init__(self, storage_dir: Path | str = "interlock_data"):
        """
        Initialize artifact store.
        
        Args:
            storage_dir: Directory to store artifacts (default: "interlock_data")
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True)
        
        self.tickets_file = self.storage_dir / "tickets.jsonl"
        self.events_file = self.storage_dir / "events.jsonl"
        
        logger.info(f"ArtifactStore initialized at {self.storage_dir}")
    
    def save_ticket(self, ticket: Ticket) -> None:
        """
        Save a ticket to storage.
        
        Args:
            ticket: Ticket to save
        """
        ticket_data = ticket.model_dump(mode="json")
        ticket_data["_saved_at"] = datetime.now().isoformat()
        
        with open(self.tickets_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(ticket_data, default=str) + "\n")
        
        logger.info(f"Ticket saved: ticket_id={ticket.ticket_id}, state={ticket.state}")
    
    def get_ticket(self, ticket_id: str) -> Optional[Ticket]:
        """
        Retrieve a ticket by ID (returns the most recent version).
        
        Args:
            ticket_id: Ticket ID to retrieve
            
        Returns:
            Ticket if found, None otherwise
        """
        if not self.tickets_file.exists():
            return None
        
        # Read from end to find most recent
        tickets = []
        with open(self.tickets_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        data = json.loads(line)
                        if data.get("ticket_id") == ticket_id:
                            tickets.append(data)
                    except json.JSONDecodeError:
                        continue
        
        if not tickets:
            return None
        
        # Return most recent (last in file)
        latest = tickets[-1]
        # Remove internal fields
        latest.pop("_saved_at", None)
        return Ticket(**latest)
    
    def save_event(
        self,
        run_id: str,
        event_type: str,
        state: str,
        details: dict | None = None,
    ) -> None:
        """
        Save an event to storage.
        
        Args:
            run_id: Run identifier
            event_type: Type of event (e.g., "gate_passed", "transition", "tool_call")
            state: Current state
            details: Additional event details
        """
        event = {
            "run_id": run_id,
            "event_type": event_type,
            "state": state,
            "timestamp": datetime.now().isoformat(),
            "details": details or {},
        }
        
        with open(self.events_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, default=str) + "\n")
        
        logger.info(f"Event saved: run_id={run_id}, type={event_type}, state={state}")
