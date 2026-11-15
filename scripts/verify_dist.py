"""Install each built distribution outside the checkout, then test the wheel."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import venv


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('directory',type=Path)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    archives=sorted(args.directory.resolve().glob('*.whl'))+sorted(args.directory.resolve().glob('*.tar.gz'))
    if len(archives)!=2:
        raise SystemExit('Expected exactly one wheel and one sdist')
    env={k:v for k,v in os.environ.items() if k!='PYTHONPATH'}
    for artifact in archives:
        with tempfile.TemporaryDirectory(prefix='jws-dist-') as directory:
            work=Path(directory)
            venv.create(work/'venv',with_pip=True)
            python=work/'venv/bin/python'
            def run(*command):
                subprocess.run(command,cwd=work,env=env,check=True,timeout=300)
            run(str(python),'-m','pip','install','--disable-pip-version-check','-r',str(root/'requirements.lock'),str(artifact)+'[dev]')
            run(str(python),'-m','pip','check')
            run(str(python),'-m','jarvis_home.check')
            if artifact.suffix=='.whl':
                shutil.copytree(root/'tests',work/'tests',ignore=shutil.ignore_patterns('__pycache__'))
                shutil.copytree(root/'scripts',work/'scripts',ignore=shutil.ignore_patterns('__pycache__'))
                run(str(python),'-m','pytest','-q','tests')
            print(f'Installed distribution passed: {artifact.name}',flush=True)


if __name__=='__main__':
    main()
