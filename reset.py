"""Start over: fresh database at 1204 likes, crash markers cleared."""

import chaos
import db

db.reset()
chaos.clear()
print(f"reset: {db.SEED_LIKES} likes, no notifications")
