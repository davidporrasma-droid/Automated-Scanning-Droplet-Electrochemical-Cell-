
from concurrent.futures import ThreadPoolExecutor


def run_in_worker(function, *args, **kwargs):
    """Execute a synchronous measurement outside Jupyter's event loop."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(function, *args, **kwargs)
        return future.result()
