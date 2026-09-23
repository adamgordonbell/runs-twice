from activities import notify_creator, update_like_count
from orchestrator import Context
from shared import LikeEvent


def like_workflow(ctx: Context, input: dict) -> int:
    """What a like causes. The orchestrator records each finished step, so a new worker resumes where the last one died."""
    event = LikeEvent(**input)
    count = ctx.step("update_like_count", update_like_count, event.video)
    ctx.step("notify_creator", notify_creator, event)
    return count
