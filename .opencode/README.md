# Local toolchain

Use installed Node 24 for repository JavaScript commands when compatible. Otherwise
use `node:24` through the Bash tool and standard Docker CLI, with a 300-second
in-container deadline and a Bash timeout of at least 330000 ms.

Mount only this repository at `/workspace`, preserve the caller's numeric UID/GID,
use a disposable writable HOME, `--rm --init`, and a unique container name.
Inspect/remove the exact task-owned container after cancellation or ambiguous completion.
No custom runtime manifest or additional SDK skill is required for Node.
