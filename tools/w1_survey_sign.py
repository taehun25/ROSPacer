"""Root-only module signing. Does not enroll keys, install, or reload modules.

The private key remains root-readable on its originating laptop. The public
certificate must be enrolled by the operator through the firmware MOK screen.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def run(argv):
    q = subprocess.run(argv,capture_output=True,text=True,timeout=40)
    if q.returncode:
        raise RuntimeError(q.stderr)
    return q.stdout.strip()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--folder', type=Path, required=True)
    a = p.parse_args()
    folder = a.folder.resolve()
    if os.geteuid() != 0 or folder.parts[-3:] != ('w1_completion_readiness','survey_driver_fix','staged'):
        raise ValueError('root and exact staged artifact path required')
    build = json.loads((folder/'build_result.json').read_text())
    kernel = os.uname().release
    if kernel != build['kernel'] or build['installed'] or build['loaded']:
        raise ValueError('only sign uninstalled matching-kernel build')
    certdir = Path('/var/lib/rospacer-survey')
    certdir.mkdir(mode=0o700, exist_ok=True)
    os.chmod(certdir,0o700)
    key, cert = certdir/'MOK.priv', certdir/'MOK.der'
    if key.exists() != cert.exists():
        raise ValueError('incomplete signing key pair')
    if not key.exists():
        os.umask(0o077)
        run(['openssl','req','-new','-x509','-newkey','rsa:3072','-nodes','-days','3650',
             '-subj','/CN=ROSPacer survey '+os.uname().nodename+'/',
             '-addext','keyUsage=critical,digitalSignature',
             '-addext','extendedKeyUsage=codeSigning,1.3.6.1.4.1.2312.16.1.2',
             '-outform','DER','-keyout',str(key),'-out',str(cert)])
    os.chmod(key,0o600)
    source = folder/'source'/('ubuntu_'+kernel.split('-')[1])/'mt76'
    signing_tool = Path('/lib/modules')/kernel/'build/scripts/sign-file'
    result = {'kernel':kernel,'certificate_path':str(cert),'key_path':str(key),
              'certificate_sha256':hashlib.sha256(cert.read_bytes()).hexdigest(),
              'certificate_info':run(['openssl','x509','-inform','DER','-in',str(cert),'-noout','-subject','-fingerprint','-sha256']),
              'modules':{},'enrolled':False,'installed':False,'loaded':False}
    for rel, metadata in build['modules'].items():
        path = source/rel
        if not path.resolve().is_relative_to(source) or hashlib.sha256(path.read_bytes()).hexdigest() != metadata['sha256_unsigned']:
            raise ValueError('unsigned build hash mismatch: '+rel)
        run([str(signing_tool),'sha256',str(key),str(cert),str(path)])
        signer = run(['modinfo','-F','signer',str(path)])
        if signer != 'ROSPacer survey '+os.uname().nodename:
            raise ValueError('unexpected signer')
        result['modules'][rel]={'sha256_signed':hashlib.sha256(path.read_bytes()).hexdigest(),'signer':signer,
                                'signature_id':run(['modinfo','-F','sig_id',str(path)])}
    env = dict(os.environ, LC_ALL='C')
    q = subprocess.run(['mokutil','--test-key',str(cert)],capture_output=True,text=True,timeout=10,env=env)
    # This mokutil returns 0 for absent and 1 for present; check its explicit
    # result instead of treating the return code as conventional success.
    result['enrolled'] = q.returncode in (0, 1) and (' is already enrolled' in q.stdout or ' is enrolled' in q.stdout)
    result['enrollment_check'] = {'rc':q.returncode,'stdout':q.stdout,'stderr':q.stderr}
    (folder/'sign_result.json').write_text(json.dumps(result,indent=2))
    os.chmod(folder/'sign_result.json',0o644)
    print(json.dumps(result),flush=True)


if __name__ == '__main__':
    main()
