"""A file-backed lock shared by threads and API worker processes."""
import errno
import os
import threading
import time


class ProcessLock:
    def __init__(self, path):
        self.path = path
        self._local = threading.Lock()
        self._file = None

    def acquire(self, blocking=True):
        if not self._local.acquire(blocking=blocking):
            return False
        handle = None
        try:
            path = self.path()
            path.parent.mkdir(parents=True, exist_ok=True)
            handle = path.open("a+b")
            if path.stat().st_size == 0:
                handle.write(b"0")
                handle.flush()
            while True:
                try:
                    handle.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self._file = handle
                    return True
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    if not blocking:
                        handle.close()
                        self._local.release()
                        return False
                    time.sleep(0.05)
        except BaseException:
            if handle is not None:
                handle.close()
            self._local.release()
            raise

    def release(self):
        if self._file is None:
            raise RuntimeError("Lock is not acquired")
        try:
            # Closing the descriptor releases the OS lock, including on Windows.
            self._file.close()
        finally:
            self._file = None
            self._local.release()
