"""Types shared by the server, workflow and activities."""

from dataclasses import dataclass


@dataclass
class LikeEvent:
    user: str
    video: str

    @property
    def event_id(self) -> str:
        """Stable: the same like always has the same ID. Used as the job ID and the notification key."""
        return f"like-{self.user}-{self.video}"
