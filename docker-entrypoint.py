"""Container entrypoint.

The backend is stateless (data lives in MySQL, images in the object storage)
and runs as the unprivileged ``appuser`` set in the Dockerfile.
"""

import os
import sys

if __name__ == "__main__":
    port = os.environ.get("PORT", "8000")
    host = os.environ.get("FIHI_HOST", "::")  # dual stack (Railway private network is IPv6)
    os.execv(  # noqa: S606 - fixed argv, no shell
        sys.executable,
        [sys.executable, "server.py", "--host", host, "--port", port],
    )
