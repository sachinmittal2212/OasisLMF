import gc
from functools import wraps


def force_gc_collect(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        res = fn(*args, **kwargs)
        gc.collect()
        return res

    return wrapper
