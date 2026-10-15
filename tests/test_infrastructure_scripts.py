"""
The shell suites for the scripts that change peers on the entry node, run
from pytest so CI runs them: the wrappers the portal calls (pwa-add-peer,
pwa-del-peer) and tools/peer-remove.sh, all against a fake `awg` in a temp
directory. test_trial_net.sh is not here: it needs root and network
namespaces, which a CI runner does not give.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).parent / "infrastructure"


@pytest.mark.skipif(not shutil.which("bash"), reason="no bash")
@pytest.mark.parametrize("suite", ["test_wrappers.sh", "test_peer_remove.sh"])
def test_shell_suite(suite):
    p = subprocess.run(["bash", str(HERE / suite)], capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, p.stdout[-4000:] + p.stderr[-2000:]
    assert " 0 failed" in p.stdout
