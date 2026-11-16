#!/bin/sh
set -eu
# This unique project and its volume are owned exclusively by this test invocation.
project="jws-test-$(python3 -c 'import uuid; print(uuid.uuid4().hex[:12])')"
compose() {
  docker compose -p "$project" -f deploy/community/compose.yaml -f deploy/community/compose.test.yaml "$@"
}
cleanup() { compose down -v --remove-orphans; }
trap cleanup EXIT
compose config --quiet
compose build
compose run --rm -T household python -c 'import os; from pathlib import Path; assert os.getuid()==10001; assert Path("/data").stat().st_uid==10001; assert Path("/data").stat().st_mode & 0o077==0; assert not os.access("/opt/jws",os.W_OK); print("container permissions passed")'
compose run --rm -T household jarvis-home-check --parent /data
