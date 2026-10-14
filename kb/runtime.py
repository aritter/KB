"""One local inference slot shared by Qwen and Kev, including separate CLI processes."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import tempfile
import time


@contextmanager
def inference_slot(seconds):
    started = time.monotonic()
    path = Path(tempfile.gettempdir()) / ('editable-kb-model-' + str(os.getuid()) + '.lock')
    with path.open('a') as lock:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                remaining = seconds - (time.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError('Shared inference slot budget exhausted')
                time.sleep(min(0.05, remaining))
        try:
            remaining = seconds - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError('Shared inference slot budget exhausted')
            yield remaining
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
