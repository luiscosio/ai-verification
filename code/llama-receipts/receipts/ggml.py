"""Read ggml tensors from Python through the libraries llama-cpp-python ships.

Only what the tracer needs: the `ggml_tensor` struct layout (checked against
`ggml_get_name` and `ggml_nbytes` at first use), a few exported helpers, and
`ggml_backend_tensor_get` to copy tensor bytes out of any backend buffer.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from pathlib import Path

import llama_cpp

GGML_MAX_DIMS = 4
GGML_MAX_SRC = 10
GGML_MAX_OP_PARAMS = 64
GGML_MAX_NAME = 64

# Ops that only reinterpret memory. They compute nothing, so the trace resolves
# them to the tensor they view instead of recording them as nodes.
LAYOUT_OPS = frozenset({"NONE", "RESHAPE", "VIEW", "PERMUTE", "TRANSPOSE"})


class GgmlTensor(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("buffer", ctypes.c_void_p),
        ("ne", ctypes.c_int64 * GGML_MAX_DIMS),
        ("nb", ctypes.c_size_t * GGML_MAX_DIMS),
        ("op", ctypes.c_int),
        ("op_params", ctypes.c_int32 * (GGML_MAX_OP_PARAMS // 4)),
        ("flags", ctypes.c_int32),
        ("src", ctypes.c_void_p * GGML_MAX_SRC),
        ("view_src", ctypes.c_void_p),
        ("view_offs", ctypes.c_size_t),
        ("data", ctypes.c_void_p),
        ("name", ctypes.c_char * GGML_MAX_NAME),
        ("extra", ctypes.c_void_p),
        ("padding", ctypes.c_char * 8),
    ]


TensorPtr = ctypes.POINTER(GgmlTensor)

_lib = None


def lib() -> ctypes.CDLL:
    """libggml-base from the llama-cpp-python wheel, with the signatures we use."""
    global _lib
    if _lib is not None:
        return _lib
    libdir = Path(llama_cpp.__file__).parent / "lib"
    candidates = sorted(libdir.glob("libggml-base.*")) + sorted(libdir.glob("libggml-base*.so*"))
    if not candidates:
        raise RuntimeError(f"libggml-base not found under {libdir}")
    g = ctypes.CDLL(str(candidates[0]))
    g.ggml_nbytes.restype, g.ggml_nbytes.argtypes = ctypes.c_size_t, [ctypes.c_void_p]
    g.ggml_get_name.restype, g.ggml_get_name.argtypes = ctypes.c_char_p, [ctypes.c_void_p]
    g.ggml_op_desc.restype, g.ggml_op_desc.argtypes = ctypes.c_char_p, [ctypes.c_void_p]
    g.ggml_op_name.restype, g.ggml_op_name.argtypes = ctypes.c_char_p, [ctypes.c_int]
    g.ggml_type_name.restype, g.ggml_type_name.argtypes = ctypes.c_char_p, [ctypes.c_int]
    g.ggml_is_contiguous.restype, g.ggml_is_contiguous.argtypes = ctypes.c_bool, [ctypes.c_void_p]
    g.ggml_backend_tensor_get.restype = None
    g.ggml_backend_tensor_get.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t]
    _lib = g
    return g


@dataclass
class TensorInfo:
    """A snapshot of a tensor's metadata. `ptr` is only valid inside the callback."""

    ptr: int
    name: str
    type: str
    op: str  # ggml_op_desc: op name, or the unary/glu op name for UNARY/GLU
    op_name: str  # plain ggml_op name
    ne: list[int]
    nb: list[int]
    nbytes: int
    op_params: bytes
    data: int
    view_src: int
    srcs: list[int]

    @property
    def is_layout(self) -> bool:
        return self.op_name in LAYOUT_OPS

    @property
    def is_leaf(self) -> bool:
        return self.op_name == "NONE"

    def to_dict(self) -> dict:
        return {"name": self.name, "type": self.type, "ne": self.ne, "nb": self.nb}


def info(ptr: int) -> TensorInfo:
    g = lib()
    t = ctypes.cast(ptr, TensorPtr).contents
    return TensorInfo(
        ptr=ptr,
        name=t.name.split(b"\0")[0].decode(errors="replace"),
        type=g.ggml_type_name(t.type).decode(),
        op=g.ggml_op_desc(ptr).decode(),
        op_name=g.ggml_op_name(t.op).decode(),
        ne=[int(x) for x in t.ne],
        nb=[int(x) for x in t.nb],
        nbytes=int(g.ggml_nbytes(ptr)),
        op_params=bytes(t.op_params),
        data=t.data or 0,
        view_src=t.view_src or 0,
        srcs=[int(s) for s in t.src if s],
    )


def check_layout(ptr: int) -> None:
    """Fail loudly if the struct layout above disagrees with the loaded library."""
    g = lib()
    t = ctypes.cast(ptr, TensorPtr).contents
    name = t.name.split(b"\0")[0]
    if g.ggml_get_name(ptr) != name:
        raise RuntimeError("ggml_tensor struct layout mismatch: name field")
    if t.data is None and t.view_src is None and g.ggml_nbytes(ptr) > 0 and t.buffer is not None:
        raise RuntimeError("ggml_tensor struct layout mismatch: data pointer")


def base_of(ptr: int) -> int:
    """Follow `view_src` to the tensor that owns the memory."""
    while True:
        t = ctypes.cast(ptr, TensorPtr).contents
        if not t.view_src:
            return ptr
        ptr = t.view_src


def read_bytes(ptr: int, nbytes: int | None = None) -> bytes:
    """Copy a tensor's bytes (the span `ggml_nbytes` covers) out of its backend buffer."""
    g = lib()
    n = int(g.ggml_nbytes(ptr)) if nbytes is None else nbytes
    buf = ctypes.create_string_buffer(n)
    g.ggml_backend_tensor_get(ptr, buf, 0, n)
    return buf.raw


def eval_callback(fn):
    """Wrap `fn(tensor_ptr, ask) -> bool` as a `ggml_backend_sched_eval_callback`."""
    import llama_cpp.llama_cpp as C

    def wrapper(ptr, ask, _user_data):
        return bool(fn(ptr, ask))

    return C.ggml_backend_sched_eval_callback(wrapper)


class context_params_with_callback:
    """Patch `llama_context_default_params` so the next `Llama(...)` gets `cb_eval`.

    llama-cpp-python builds the context inside `Llama.__init__` from the default
    params, and there is no setter after creation, so this is the hook.
    """

    def __init__(self, callback):
        self.callback = callback
        self._orig = None

    def __enter__(self):
        import llama_cpp.llama_cpp as C

        self._orig = C.llama_context_default_params
        cb = self.callback

        def patched():
            p = self._orig()
            p.cb_eval = cb
            p.cb_eval_user_data = None
            return p

        C.llama_context_default_params = patched
        return self

    def __exit__(self, *exc):
        import llama_cpp.llama_cpp as C

        C.llama_context_default_params = self._orig
        return False
