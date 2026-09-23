import os
import signal

from orchestrator import Orchestrator
from workflows import like_workflow

if __name__ == "__main__":
    print(f"CRASH_AT={os.environ.get('CRASH_AT', '')!r} COUNT_MODE={os.environ.get('COUNT_MODE', 'set')!r}", flush=True)
    # Ctrl-C kills the worker outright, like a crash, instead of shutting down cleanly.
    signal.signal(signal.SIGINT, lambda *_: os._exit(130))
    Orchestrator({"like": like_workflow}).run_forever()
