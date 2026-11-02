#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Download and instantiate the static CJK fonts used by build_pdfs.py.

The variable fonts live in google/fonts (SIL Open Font License).  This script
fetches them through the authenticated `gh` CLI (GitHub blob API), then uses
fontTools to pin static Regular/Bold instances, which ReportLab embeds without
needing a variable-font rasteriser.

Usage:
    FDE_ASSETS=/home/user/assets python3 tools/prepare_fonts.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ASSETS = Path(os.environ.get("FDE_ASSETS", "/home/user/assets"))
FONTS = ASSETS / "fonts"

# (path in google/fonts, blob SHA, [(weight, output name), ...])
JOBS = [
    ("ofl/notosanssc/NotoSansSC[wght].ttf",
     "fb0637bafbcd804fe32152370a1225990745b4bc",
     [(400, "NotoSansSC-Regular.ttf"), (700, "NotoSansSC-Bold.ttf")]),
    ("ofl/notoserifsc/NotoSerifSC[wght].ttf",
     "eab063faf229160a52d3760f5555150e4eb9e5bf",
     [(400, "NotoSerifSC-Regular.ttf"), (700, "NotoSerifSC-Bold.ttf")]),
    ("ofl/jetbrainsmono/JetBrainsMono[wght].ttf",
     "aa310be8b717fe3774f9444dd89d5f4101cc6d10",
     [(400, "JetBrainsMono-Regular.ttf")]),
]


def main():
    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont

    FONTS.mkdir(parents=True, exist_ok=True)
    for repo_path, sha, outputs in JOBS:
        var_path = FONTS / (Path(repo_path).stem + "-var.ttf")
        if not var_path.exists():
            print(f"Fetching {repo_path} ...", flush=True)
            cmd = ["gh", "api", "-X", "GET",
                   f"repos/google/fonts/git/blobs/{sha}",
                   "-H", "Accept: application/vnd.github.raw"]
            with open(var_path, "wb") as f:
                subprocess.run(cmd, stdout=f, check=True)
        base = TTFont(str(var_path))
        for weight, out_name in outputs:
            out = FONTS / out_name
            if out.exists():
                print(f"  exists: {out.name}")
                continue
            inst = instantiateVariableFont(base, {"wght": weight},
                                           inplace=False, optimize=True)
            inst.save(str(out))
            print(f"  wrote:  {out.name} ({out.stat().st_size // 1024} KB)")
    print("Fonts ready in", FONTS)
    print("Cover images (cover_book.png / cover_synthesis.png) are generated "
          "artwork and must be placed in", ASSETS, "separately.")


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as e:
        sys.exit(f"Missing dependency (fontTools or gh CLI): {e}")
