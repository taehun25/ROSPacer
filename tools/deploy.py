"""Deploy this workspace mirror to the explicitly identified SR2 laptops."""
import io
import json
import ipaddress
import os
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
KEY = str(Path.home()/".ssh/id_ed25519_rpbench")
HOSTS = {"12": ("192.168.0.12", "csi2@192.168.0.3"),
         "10": ("192.168.0.10", "csi@192.168.0.4")}
REMOTE = "ros2_ws/src/large_data_1009/ROSPacer"


def ssh(host, command, data=None):
    alias, account = HOSTS[host]
    # Management NIC addresses can change between laboratory sessions.
    bind = os.environ.get("ROSPACER_SSH_BIND", "192.168.0.2")
    if ipaddress.ip_address(bind).version != 4:
        raise ValueError("ROSPACER_SSH_BIND requires an IPv4 address")
    return subprocess.run(["ssh", "-b", bind, "-i", KEY,
        "-o", "HostKeyAlias="+alias, "-o", "StrictHostKeyChecking=yes",
        "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", account, command],
        input=data, capture_output=True, timeout=60)


def deploy():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as archive:
        for folder in ("rospacer", "tools", "tests", "reference", ".github"):
            for path in (ROOT/folder).rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts:
                    archive.add(path, arcname=path.relative_to(ROOT))
        for name in ("README.md", "STATUS.md", "EXECUTION_PLAN.md", "THIRD_PARTY_NOTICES.md", "pyproject.toml", ".gitignore", ".gitattributes"):
            if (ROOT/name).exists():
                archive.add(ROOT/name, arcname=name)
    script = "import pathlib,sys,tarfile; p=pathlib.Path.home()/'"+REMOTE+"'; p.mkdir(parents=True,exist_ok=True); tarfile.open(fileobj=sys.stdin.buffer,mode='r|gz').extractall(p); print(p)"
    for host in HOSTS:
        p = ssh(host, 'python3 -c "'+script+'"', buf.getvalue())
        print(host, p.returncode, p.stdout.decode(), p.stderr.decode())
        if p.returncode:
            raise RuntimeError("deployment failed")


if __name__ == "__main__":
    deploy()
