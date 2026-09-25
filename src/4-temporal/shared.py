"""Types shared by the server, workflow, activities and worker.

Imported into the workflow sandbox, so keep it free of I/O and environment reads.
"""

from dataclasses import dataclass

TASK_QUEUE = "likes"


@dataclass
class LikeEvent:
    user: str
    video: str

    @property
    def event_id(self) -> str:
        """Stable: the same like always has the same ID. Used as the workflow ID and the notification key."""
        return f"like-{self.user}-{self.video}"
