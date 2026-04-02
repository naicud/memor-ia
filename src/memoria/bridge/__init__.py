"""MEMORIA bridge — protocol bridge and task event integration."""

from memoria.bridge.protocol import ProtocolBridge
from memoria.bridge.events import TaskEventBridge

__all__ = [
    "ProtocolBridge",
    "TaskEventBridge",
]
