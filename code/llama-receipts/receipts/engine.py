"""Thin wrapper over llama-cpp-python that exposes logits for our own sampler."""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass

import numpy as np


@dataclass
class EngineOptions:
    n_gpu_layers: int = -1  # -1 = all layers on the GPU (Metal here); 0 = CPU only
    n_threads: int | None = None
    n_ctx: int = 1024
    n_batch: int = 512
    flash_attn: bool = False

    def to_dict(self) -> dict:
        return {
            "n_gpu_layers": self.n_gpu_layers,
            "n_threads": self.n_threads or os.cpu_count(),
            "n_ctx": self.n_ctx,
            "n_batch": self.n_batch,
            "flash_attn": self.flash_attn,
        }


class Engine:
    def __init__(self, model_path: str, opts: EngineOptions | None = None, tracer=None):
        import llama_cpp

        self.opts = opts or EngineOptions()
        self.model_path = model_path
        self._llama_cpp = llama_cpp
        self.tracer = tracer
        self._cb = None
        hook = contextlib.nullcontext()
        if tracer is not None:
            from receipts import ggml

            self._cb = ggml.eval_callback(tracer.callback)  # keep a reference or ctypes frees it
            hook = ggml.context_params_with_callback(self._cb)
        with hook:
            self.llm = llama_cpp.Llama(
                model_path=model_path,
                n_ctx=self.opts.n_ctx,
                n_batch=self.opts.n_batch,
                n_ubatch=self.opts.n_batch,  # one graph per eval call, so the tracer's graph index is exact
                n_threads=self.opts.n_threads,
                n_threads_batch=self.opts.n_threads,
                n_gpu_layers=self.opts.n_gpu_layers,
                flash_attn=self.opts.flash_attn,
                logits_all=True,
                verbose=False,
            )

    # --- tokens ---------------------------------------------------------
    def tokenize(self, text: str, add_bos: bool = True) -> list[int]:
        return self.llm.tokenize(text.encode("utf-8"), add_bos=add_bos, special=True)

    def detokenize(self, tokens: list[int]) -> str:
        return self.llm.detokenize(tokens, special=True).decode("utf-8", "replace")

    def is_end_of_generation(self, token: int) -> bool:
        model = getattr(self.llm, "_model", None)
        if model is not None and hasattr(model, "token_is_eog"):
            return bool(model.token_is_eog(token))
        return token == self.llm.token_eos()

    @property
    def n_vocab(self) -> int:
        return int(self.llm.n_vocab())

    # --- decoding -------------------------------------------------------
    def reset(self) -> None:
        """Forget the context and zero the KV cache, so every run starts from the same state."""
        self.llm.reset()
        ctx = getattr(self.llm, "_ctx", None)
        if ctx is not None and hasattr(ctx, "kv_cache_clear"):
            ctx.kv_cache_clear()

    def feed(self, tokens: list[int]) -> np.ndarray:
        """Append `tokens` to the context and return the logits after the last one."""
        if self.tracer is not None:
            if len(tokens) > self.opts.n_batch:
                raise ValueError(f"traced runs need the prompt in one batch: {len(tokens)} tokens > n_batch {self.opts.n_batch}")
            self.tracer.begin_graph()
        self.llm.eval(tokens)
        return np.array(self.llm.scores[self.llm.n_tokens - 1], dtype=np.float32)

    def logits_for_sequence(self, tokens: list[int], first: int) -> np.ndarray:
        """Teacher-force `tokens` in one batched pass.

        Returns logits at positions first-1 .. len(tokens)-2, i.e. the
        predictions for tokens[first:], as an array of shape (len - first, vocab).
        """
        self.reset()
        if self.tracer is not None:
            self.tracer.begin_graph()
        self.llm.eval(tokens)
        return np.array(self.llm.scores[first - 1 : len(tokens) - 1], dtype=np.float32)

    # --- metadata -------------------------------------------------------
    def info(self) -> dict:
        lc = self._llama_cpp
        sysinfo = ""
        fn = getattr(lc.llama_cpp, "llama_print_system_info", None)
        if fn is not None:
            raw = fn()
            sysinfo = raw.decode() if isinstance(raw, bytes) else str(raw)
        return {
            "name": "llama.cpp via llama-cpp-python",
            "llama_cpp_python": getattr(lc, "__version__", "unknown"),
            "system_info": sysinfo,
            "backend": "gpu" if self.opts.n_gpu_layers != 0 else "cpu",
            "options": self.opts.to_dict(),
            "model_metadata": {k: v for k, v in getattr(self.llm, "metadata", {}).items() if len(str(v)) < 200},
        }
