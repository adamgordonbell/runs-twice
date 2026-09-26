"""Imported into the workflow sandbox, so no I/O here."""

from dataclasses import dataclass

TASK_QUEUE = "likes"


@dataclass
class LikeEvent:
    user: str
    video: str

    @property
    def event_id(self) -> str:
        """The same like always gets the same ID: the workflow ID and the notification key."""
        return f"like-{self.user}-{self.video}"
