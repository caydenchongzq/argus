# Rebuild skill/argus-brand/assets/icons/argus-icons.svg from lucide-static (pinned).
# 1) cd /tmp && npm pack lucide-static@1.70.0 lucide@1.70.0 && tar xzf lucide-static-1.70.0.tgz
# 2) add names below, run: python3 src/build_icons.py /tmp/package
import re, sys
P = (sys.argv[1] if len(sys.argv) > 1 else "/tmp/lucidepkg/ls/package") + "/icons"
import os; S = os.path.dirname(os.path.abspath(__file__))
names = "play refresh-cw check x trash-2 download settings search triangle-alert info circle-check circle-x eye sun moon monitor inbox wallet chevron-down chevron-right trending-up trending-down arrow-up-down loader-circle filter external-link copy plus pencil save upload clock calendar bell".split()
out = ['<?xml version="1.0" encoding="utf-8"?>', '<!-- Argus icon sprite: subset of lucide-static v1.70.0 (ISC, see LICENSE). Regenerate with src/build_icons.py -->', '<svg xmlns="http://www.w3.org/2000/svg">']
for n in names:
    s = open(f"{P}/{n}.svg").read()
    inner = re.sub(r"\s*\n\s*", "", s[s.index(">", s.index("<svg")) + 1:s.rindex("</svg>")].strip())
    out.append(f'  <symbol id="{n}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{inner}</symbol>')
out.append("</svg>")
open(f"{S}/argus-icons.svg", "w").write("\n".join(out) + "\n")
