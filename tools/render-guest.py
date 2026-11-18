#!/usr/bin/env python3
"""Render guest templates for static parsing without credentials or a running lab."""
from pathlib import Path
import argparse, json, sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from akl.config import Config,example
from akl.guest import render_script
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
c=Config(example(),Path('/unused/config.json'))
c.data['media']['openssh']={'sha256':json.loads((ROOT/'media.lock.json').read_text())['openssh']['sha256']}
a.output.mkdir(parents=True,exist_ok=True)
for source in (ROOT/'guest').glob('*.ps1'):
    (a.output/source.name).write_text(render_script(c,source.read_text()))
print(json.dumps({'rendered':len(list(a.output.glob('*.ps1'))),'directory':str(a.output)}))
