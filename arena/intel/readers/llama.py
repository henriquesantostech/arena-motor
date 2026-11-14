"""Thin wrapper around a pinned llama.cpp server: start, wait until ready, call, stop.

Deterministic settings (greedy decoding, fixed seed, fixed threads and batch) and grammar-constrained JSON via
json_schema. CPU flags are logged with every reading so drift between runners can be explained.
"""
import json
import os
import platform
import subprocess
import time
from pathlib import Path

import requests

from ... import config


def cfg():
    return json.loads((config.RULES_DIR / "readers.json").read_text(encoding="utf-8"))


def cpu_flags():
    try:
        txt = Path("/proc/cpuinfo").read_text()
        model = next((l.split(":", 1)[1].strip() for l in txt.splitlines() if l.startswith("model name")), "")
        flags = next((l.split(":", 1)[1].split() for l in txt.splitlines() if l.startswith("flags")), [])
        keep = [f for f in flags if f in ("avx", "avx2", "avx512f", "avx512_vnni", "avx_vnni", "fma", "f16c", "amx_int8")]
        return f"{model} | {' '.join(keep)}"
    except OSError:
        return platform.processor() or platform.machine()


class Server:
    def __init__(self, models_dir, model_file, embedding=False, port=8089, ctx=None):
        rt = cfg()["runtime"]["llama_cpp"]
        self.flags = rt["flags"]
        self.port = port
        binary = os.environ.get("LLAMA_SERVER") or str(Path(models_dir) / "llama" / "llama-server")
        args = [binary, "-m", str(Path(models_dir) / model_file), "--port", str(port), "--host", "127.0.0.1",
                "-t", str(self.flags["threads"]), "-b", str(self.flags["batch"]), "-c", str(ctx or self.flags["ctx"]),
                "--seed", str(self.flags["seed"]), "-np", "1", "--no-webui"]
        if embedding:
            args += ["--embedding", "--pooling", "mean", "-ub", "2048", "-b", "2048"]
        self.runtime = {"llama_cpp": rt["release"], "threads": self.flags["threads"], "batch": self.flags["batch"],
                        "seed": self.flags["seed"], "cpu": cpu_flags()}
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.url = f"http://127.0.0.1:{port}"
        for _ in range(600):
            try:
                if requests.get(f"{self.url}/health", timeout=2).status_code == 200:
                    return
            except requests.RequestException:
                pass
            if self.proc.poll() is not None:
                raise RuntimeError("llama-server exited")
            time.sleep(1)
        raise RuntimeError("llama-server not ready")

    def complete(self, prompt, schema=None, max_tokens=512):
        body = {"prompt": prompt, "n_predict": max_tokens, "temperature": self.flags["temperature"],
                "top_k": self.flags["top_k"], "seed": self.flags["seed"], "cache_prompt": False}
        if schema:
            body["json_schema"] = schema
        r = requests.post(f"{self.url}/completion", json=body, timeout=900)
        r.raise_for_status()
        js = r.json()
        return js.get("content", ""), js.get("timings", {})

    def chat(self, system, user, schema=None, max_tokens=512):
        """Chat template applied by the server (Qwen3.5); thinking disabled for short, deterministic outputs."""
        body = {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "max_tokens": max_tokens, "temperature": self.flags["temperature"], "top_k": self.flags["top_k"],
                "seed": self.flags["seed"], "chat_template_kwargs": {"enable_thinking": False}}
        if schema:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "reading", "schema": schema,
                                                                               "strict": True}}
        r = requests.post(f"{self.url}/v1/chat/completions", json=body, timeout=1800)
        r.raise_for_status()
        js = r.json()
        return js["choices"][0]["message"]["content"], js.get("timings", js.get("usage", {}))

    def embed(self, texts, dims=256):
        r = requests.post(f"{self.url}/v1/embeddings", json={"input": texts}, timeout=900)
        r.raise_for_status()
        out = []
        for d in sorted(r.json()["data"], key=lambda x: x["index"]):
            v = d["embedding"][:dims]                     # Matryoshka truncation
            n = sum(x * x for x in v) ** 0.5 or 1.0
            out.append([round(x / n, 6) for x in v])
        return out

    def close(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(20)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
