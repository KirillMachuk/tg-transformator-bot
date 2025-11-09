from enum import Enum, auto


class ConversationState(Enum):
    WELCOME = auto()
    SKILL_LEVEL = auto()
    VIDEO = auto()
    DIAGNOSIS = auto()
    READINESS = auto()
    REPORT = auto()
    CHAT = auto()
