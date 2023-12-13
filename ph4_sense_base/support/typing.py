try:
    from typing import Any, Callable, Dict, List, Optional, Tuple, Union
except ImportError:
    Any = type(str)
    Optional = type(None)
    Union = type(None)
    Dict = type(None)
    Tuple = type(None)
    List = type(None)
    Callable = type(None)
