"""Check the environment against the lock; export reviewable license metadata."""
import argparse
import hashlib
from importlib.metadata import distribution
import json
from pathlib import Path
import tomllib

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def inventory(root):
    project=tomllib.loads((root/'pyproject.toml').read_text())['project']
    pins={}
    for line in (root/'requirements.lock').read_text().splitlines():
        if line and not line.startswith('#'):
            req=Requirement(line)
            pins[canonicalize_name(req.name)]=str(req.specifier).removeprefix('==')
    runtime=set()
    def visit(requirement):
        req=Requirement(requirement)
        if req.marker and not req.marker.evaluate({'extra':''}):
            return
        name=canonicalize_name(req.name)
        if name in runtime:
            return
        runtime.add(name)
        for dependency in distribution(name).requires or []:
            visit(dependency)
    for requirement in project['dependencies']:
        visit(requirement)
    direct={canonicalize_name(Requirement(r).name) for r in project['dependencies']}
    result=[]
    for name,expected in sorted(pins.items()):
        dist=distribution(name)
        if dist.version!=expected:
            raise ValueError(f'Lock mismatch: {name}')
        for raw in dist.requires or []:
            req=Requirement(raw)
            if req.marker and not req.marker.evaluate({'extra':''}):
                continue
            key=canonicalize_name(req.name)
            if key not in pins or not req.specifier.contains(distribution(key).version):
                raise ValueError(f'Unpinned or incompatible dependency: {name} -> {key}')
        metadata=dist.metadata
        licenses=[]
        for f in dist.files or []:
            if Path(str(f)).name.lower().startswith(('license', 'copying', 'notice')) and Path(str(f)).suffix not in ('.py', '.pyc'):
                path=dist.locate_file(f)
                if path.is_file():
                    licenses.append({'path':str(f),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        declared=metadata.get('License-Expression') or metadata.get('License') or '; '.join(c for c in metadata.get_all('Classifier',[]) if c.startswith('License ::')) or 'UNKNOWN'
        result.append({'name':name,'version':dist.version,'scope':'direct-runtime' if name in direct else 'transitive-runtime' if name in runtime else 'development',
                       'declared_license':declared,'project_urls':metadata.get_all('Project-URL',[]),'license_files':licenses})
    if not runtime<=pins.keys():
        raise ValueError('Runtime closure missing from lock')
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    result=inventory(Path(__file__).resolve().parents[1])
    if args.output:
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(f'Dependency consistency passed: {len(result)} pinned distributions')


if __name__=='__main__':
    main()
