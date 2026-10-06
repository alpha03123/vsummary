"""Check cancellation independently of subprocess output."""
from contextlib import contextmanager
from threading import Event, Thread


@contextmanager
def watch_process_cancellation(process, check_cancelled, *, interval_seconds=0.1):
    stopped, cancelled = Event(), Event()
    errors = []
    def watch():
        while not stopped.wait(interval_seconds):
            if process.poll() is not None:
                return
            try:
                requested = check_cancelled()
            except Exception as error:
                errors.append(error)
                requested = True
            if requested:
                cancelled.set()
                try:
                    process.kill()
                except OSError:
                    pass
                return
    watcher = Thread(target=watch, name='download-cancellation', daemon=True)
    watcher.start()
    try:
        yield cancelled
    finally:
        stopped.set()
        watcher.join()
        if errors:
            raise errors[0]
