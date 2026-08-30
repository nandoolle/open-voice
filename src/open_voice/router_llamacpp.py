"""llama.cpp router backend (Linux): the same joint log-prob protocol as the
MLX path in listen.py — score each label (+ "\\n" terminator) as a forced
continuation of the few-shot prompt, never free-generate.

The incremental scoring reuses the prompt's KV cache and rolls it back after
each label; validated bit-exact against a clean full evaluation.
"""

import numpy as np

_llm = None


def _load(repo: str, filename: str):
    global _llm
    if _llm is None:
        import llama_cpp
        from huggingface_hub import hf_hub_download

        path = hf_hub_download(repo, filename)
        _llm = llama_cpp.Llama(
            model_path=path, n_ctx=4096, n_gpu_layers=-1, logits_all=True, verbose=False
        )
    return _llm


def _kv_rm(llm, n_keep: int) -> None:
    """Drop KV entries past n_keep (the API name varies across llama.cpp versions)."""
    import llama_cpp

    ctx = llm._ctx.ctx
    for name in ("llama_memory_seq_rm", "llama_kv_self_seq_rm", "llama_kv_cache_seq_rm"):
        fn = getattr(llama_cpp, name, None)
        if fn is not None:
            if name == "llama_memory_seq_rm":
                fn(llama_cpp.llama_get_memory(ctx), 0, n_keep, -1)
            else:
                fn(ctx, 0, n_keep, -1)
            return
    raise RuntimeError("no llama.cpp KV removal API found")


def _logsumexp(row: np.ndarray) -> float:
    m = float(row.max())
    return m + float(np.log(np.exp(row - m).sum()))


def classify(repo: str, filename: str, route_prompt: str, labels, text: str) -> str:
    llm = _load(repo, filename)
    # Qwen2.5 chat template rendered by hand, including its default system turn
    rendered = (
        "<|im_start|>system\nYou are Qwen, created by Alibaba Cloud. "
        "You are a helpful assistant.<|im_end|>\n"
        f'<|im_start|>user\n{route_prompt}"{text}" -><|im_end|>\n'
        "<|im_start|>assistant\n"
    )
    llm.reset()
    _kv_rm(llm, 0)
    llm.eval(llm.tokenize(rendered.encode(), add_bos=False, special=True))
    n0 = llm.n_tokens
    prompt_logits = np.array(llm.scores[n0 - 1], dtype=np.float64)

    best_label, best_score = "send", -float("inf")
    for label in labels:
        tokens = llm.tokenize((label + "\n").encode(), add_bos=False, special=False)
        logits, logprob = prompt_logits, 0.0
        for token in tokens:
            logprob += float(logits[token]) - _logsumexp(logits)
            llm.eval([token])
            logits = np.array(llm.scores[llm.n_tokens - 1], dtype=np.float64)
        _kv_rm(llm, n0)
        llm.n_tokens = n0
        if logprob > best_score:
            best_label, best_score = label, logprob
    return best_label
