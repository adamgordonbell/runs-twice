"""Likes a video, retrying until a response comes back. The same client for every stage."""

import argparse
import json
import time
import urllib.error
import urllib.request

ATTEMPTS = 6
TIMEOUT = 3


def post_like(url: str, user: str, video: str, lose_first_response: bool) -> None:
    body = json.dumps({"user": user, "video": video}).encode()
    for attempt in range(1, ATTEMPTS + 1):
        print(f"POST /like  attempt {attempt}")
        try:
            request = urllib.request.Request(f"{url}/like", data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                reply = json.load(response)
            if lose_first_response and attempt == 1:
                print("  (the response was lost on the way back)")
                raise TimeoutError
            print(f"  {reply}")
            return
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            print(f"  no response ({type(error).__name__}), retrying")
            time.sleep(min(2 ** (attempt - 1), 8))
    print("gave up")


def show(url: str, user: str, video: str) -> None:
    with urllib.request.urlopen(f"{url}/videos/{video}?user={user}", timeout=TIMEOUT) as response:
        state = json.load(response)
    liked = "liked" if state["liked"] else "not liked"
    print(f"{state['likes']} likes, {len(state['notifications'])} notification(s), {user}: {liked}")
    for message in state["notifications"]:
        print(f"  📬 {message}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--user", default="alice")
    parser.add_argument("--video", default="video-123")
    parser.add_argument("--lose-first-response", action="store_true")
    parser.add_argument("--show", action="store_true", help="print the video's state and exit")
    parser.add_argument("--wait", type=float, default=0, help="seconds to wait before printing the state")
    args = parser.parse_args()
    if not args.show:
        post_like(args.url, args.user, args.video, args.lose_first_response)
        time.sleep(args.wait)
    show(args.url, args.user, args.video)
