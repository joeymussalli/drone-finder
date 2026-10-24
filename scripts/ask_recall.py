r"""Ask RECALL where your things are, by typing questions in the terminal.

This is the "read" side of RECALL: a simple text loop around QueryService.
QueryService itself is I/O-free; this script supplies the input() and print()
so the same logic can later sit behind the team app's web route unchanged.

Run from the repository root:
    .\.venv\Scripts\python.exe -m scripts.ask_recall --demo

--demo pre-loads a few example sightings so you can try the question-and-answer
flow without a running camera. Type a question like "where are my keys?".
Type "objects" to list what is remembered, or "quit" to exit.
"""

import argparse
import os
import sys
import time

# Ensure the repository root is importable so ``src`` resolves no matter how
# this script is launched (``-m scripts.ask_recall`` or a direct file path).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.ObjectMemory import ObjectMemory
from src.QueryService import QueryService
from src.Sighting import Sighting

QUIT_WORDS = {"quit", "exit", "q"}
LIST_WORDS = {"objects", "list", "what do you know"}


def load_demo_memory(memory: ObjectMemory, now: float) -> None:
    """Populate memory with a few example sightings for standalone testing.

    Times are offset from `now` so the "seen ... ago" phrasing is realistic:
    keys just seen, phone a minute ago, remote several minutes ago.
    """
    memory.record(Sighting("keys", "kitchen counter", 0.92, now - 5))
    memory.record(Sighting("phone", "coffee table", 0.81, now - 40))
    memory.record(Sighting("remote control", "the sofa", 0.86, now - 90))


def run_loop(service: QueryService, memory: ObjectMemory) -> None:
    """Read questions until the user quits."""
    print("Ask RECALL where something is. Type 'objects' to list what I know,")
    print("or 'quit' to exit.\n")

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            return

        if not question:
            continue

        lowered = question.lower()
        if lowered in QUIT_WORDS:
            print("Goodbye.")
            return
        if lowered in LIST_WORDS:
            known = memory.all_objects()
            if known:
                print("RECALL: I'm currently remembering: " + ", ".join(known))
            else:
                print("RECALL: I haven't seen anything yet.")
            continue

        print("RECALL:", service.answer_question(question))


def parse_args():
    parser = argparse.ArgumentParser(description="Ask RECALL where your things are")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Pre-load example sightings so you can test without a camera",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    memory = ObjectMemory()
    if args.demo:
        load_demo_memory(memory, now=time.time())
    else:
        print(
            "Starting with empty memory. Nothing has been seen yet, so every "
            "answer will be 'not sure'. Use --demo to load example sightings."
        )

    service = QueryService(memory)
    run_loop(service, memory)
    return 0


if __name__ == "__main__":
    sys.exit(main())
