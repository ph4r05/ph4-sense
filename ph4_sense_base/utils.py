def try_fnc(x, msg=None):
    try:
        return x()
    except Exception as e:
        print(f'Err {msg or ""}: {e}')


def exec_cb(func, *args, **kwargs):
    if callable(func):
        return func(*args, **kwargs)


def try_exec_cb(func, *args, **kwargs):
    if callable(func):
        return try_fnc(lambda: func(*args, **kwargs))


def exec_method_cb(obj, method_name, *args, **kwargs):
    meth = getattr(obj, method_name, None) if obj is not None else None
    if meth is not None and callable(meth):
        return meth(*args, **kwargs)
    return None


def try_exec_method_cb(obj, method_name, *args, **kwargs):
    return try_fnc(lambda: exec_method_cb(obj, method_name, *args, **kwargs))


def dval(val, default=-1):
    return val if val is not None else default


def set_default(dict: dict, key: str, val):
    if key in dict:
        return
    dict[key] = val
