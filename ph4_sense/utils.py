def try_fnc(x, msg=None):
    try:
        return x()
    except Exception as e:
        print(f'Err {msg or ""}: {e}')


def dval(val, default=-1):
    return val if val is not None else default


def set_default(dict: dict, key: str, val):
    if key in dict:
        return
    dict[key] = val
