"""Record commit and checksums; never creates a release or uploads packages."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import tomllib


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('directory',type=Path)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    version=tomllib.loads((root/'pyproject.toml').read_text())['project']['version']
    files=sorted(p for p in args.directory.iterdir() if p.name.endswith(('.whl','.tar.gz')))
    if len(files)!=2 or any(version not in p.name for p in files):
        raise SystemExit('Version/artifact mismatch')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    manifest={'version':version,'commit':commit,'python':platform.python_version(),
              'platform':platform.system(),'architecture':platform.machine(),
              'build_inputs_dirty':bool(subprocess.check_output(['git','diff','HEAD','--',
                  'src','tests','scripts','docs/guides','docs/images','deploy/community',
                  'pyproject.toml','requirements.lock','MANIFEST.in','README.md','CHANGELOG.md','SECURITY.md','CONTRIBUTING.md'],cwd=root)),
              'sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    (args.directory/'build.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (args.directory/'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name,digest in manifest['sha256'].items()))
    print('Build manifest written')


if __name__=='__main__':
    main()
