"""MEMORIA bridge — protocol bridge and task event integration."""

from memoria.bridge.events import TaskEventBridge
from memoria.bridge.protocol import ProtocolBridge

__all__ = [
    "ProtocolBridge",
    "TaskEventBridge",
]
