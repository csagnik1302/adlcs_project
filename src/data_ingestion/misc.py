import threading
import time
import networkx as nx
import matplotlib.pyplot as plt
from openai import RateLimitError


class Throttle:
    def __init__(self, rpm, max_concurrent=2):
        self.interval = 60.0 / rpm
        self.lock = threading.Lock()
        self.next_slot = 0.0
        self.sem = threading.Semaphore(max_concurrent)

    def wait(self):
        with self.lock:
            now = time.monotonic()
            delay = max(0.0, self.next_slot - now)
            self.next_slot = max(now, self.next_slot) + self.interval
        if delay:
            time.sleep(delay)


def throttle_client(client, rpm=10, max_concurrent=2, cooldown=60):
    """Patch client.chat.completions.create so calls are rate limited."""
    throttle = Throttle(rpm, max_concurrent)
    original_create = client.chat.completions.create

    def throttled_create(*args, **kwargs):
        with throttle.sem:
            throttle.wait()
            try:
                return original_create(*args, **kwargs)
            except RateLimitError:
                time.sleep(cooldown)   # let the per-minute quota window reset
                raise                  # atlas_rag's retry will try again

    client.chat.completions.create = throttled_create
    return client



def view_graphml(file_path):
    gr=nx.read_graphml(file_path)
    nx.draw(gr)
    plt.show()


def inspect_graphml(file_path):
    
    graph=nx.read_graphml(file_path)
    n_nodes, n_edges=graph.number_of_nodes(), graph.number_of_edges()
    