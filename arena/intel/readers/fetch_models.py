"""Downloads the pinned llama.cpp build and GGUF models into a folder, verifying every SHA-256.

  python -m arena.intel.readers.fetch_models --models models --only llama,llm,embed,brief

A file whose hash does not match is deleted and the command fails: a model is never used unverified.
"""
import argparse
import hashlib
import sys
import tarfile
from pathlib import Path

import requests

from .llama import cfg

HF = "https://huggingface.co/{repo}/resolve/main/{file}"


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url, dest, sha):
    dest = Path(dest)
    if dest.exists() and _sha(dest) == sha:
        return "cached"
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=120, headers={"User-Agent": "arena-of-agents/0.2"}) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    got = _sha(tmp)
    if got != sha:
        tmp.unlink()
        raise SystemExit(f"hash mismatch for {dest.name}")
    tmp.replace(dest)
    return "downloaded"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="models")
    ap.add_argument("--only", default="llama,llm,embed,brief")
    a = ap.parse_args(argv)
    c = cfg()
    out = Path(a.models)
    out.mkdir(parents=True, exist_ok=True)
    for name in a.only.split(","):
        if name == "llama":
            rt = c["runtime"]["llama_cpp"]
            tgz = out / rt["asset"]
            print("llama", _download(rt["url"], tgz, rt["sha256"]))
            target = out / "llama"
            if not (target / "llama-server").exists():
                target.mkdir(exist_ok=True)
                with tarfile.open(tgz) as t:
                    for m in t.getmembers():
                        if m.isfile():
                            m.name = Path(m.name).name          # flatten build/bin/...
                            t.extract(m, target, filter="data")
                for f in target.iterdir():
                    f.chmod(0o755)
        else:
            rc = c["readers"][name]
            print(name, _download(HF.format(repo=rc["model"], file=rc["file"]), out / rc["file"], rc["sha256"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
