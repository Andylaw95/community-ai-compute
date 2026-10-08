"""Run explicitly; Ctrl+C shuts down the local server and its child processes."""
import argparse
from pathlib import Path
import signal
import threading

from .engine import Coordinator
from .server import make_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", type=Path, default=Path(".runtime/demo.sqlite"))
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("invalid port")
    args.db.parent.mkdir(parents=True, exist_ok=True)
    core = Coordinator(args.db)
    try:
        server, supervisor = make_server(core, args.port)
    except OSError as error:
        core.close()
        parser.exit(1, f"Cannot bind loopback server: {error}\n")
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for node in core.nodes:
            supervisor.start(node)
        print(f"LOCAL_PREVIEW=http://127.0.0.1:{server.server_port}", flush=True)
        print("CPU processes only; contribution awaits consent. Ctrl+C stops all workers. No autostart.", flush=True)
        while not stop.wait(0.25):
            supervisor.sync()
    finally:
        supervisor.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        core.close()
        print("Server and all worker processes stopped.", flush=True)


if __name__ == "__main__":
    main()
