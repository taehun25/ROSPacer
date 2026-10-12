"""Fault checks for guarded kernel-module installation (no real system calls)."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('survey_install', Path(__file__).resolve().parents[1]/'tools/w1_survey_install.py')
INSTALL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALL)


class SurveyInstallSafety(unittest.TestCase):
    def test_mokutil_zero_with_not_enrolled_refuses_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cert = root/'MOK.der'
            cert.write_bytes(b'public certificate')
            (root/'sign_result.json').write_text(json.dumps({
                'kernel':'6.8.0-138-generic', 'certificate_path':str(cert),
                'certificate_sha256':hashlib.sha256(cert.read_bytes()).hexdigest()}))
            with patch.object(INSTALL,'ROOT',root), patch.object(INSTALL.os,'uname',return_value=SimpleNamespace(release='6.8.0-138-generic'),create=True), patch.object(INSTALL,'command',return_value={'rc':0,'stdout':str(cert)+' is not enrolled\n','stderr':''}) as command:
                with self.assertRaisesRegex(ValueError,'MOK enrollment'):
                    INSTALL.begin(root)
                self.assertEqual(command.call_count,1)
            self.assertFalse((root/'install_plan.json').exists())

    def test_rebooted_kernel_mismatch_refuses_install_before_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'sign_result.json').write_text(json.dumps({'kernel':'6.8.0-136-generic'}))
            with patch.object(INSTALL.os,'uname',return_value=SimpleNamespace(release='6.8.0-138-generic'),create=True), patch.object(INSTALL,'command') as command:
                with self.assertRaisesRegex(ValueError,'running kernel'):
                    INSTALL.begin(root)
                command.assert_not_called()

    def test_changed_module_rolls_back_before_unloading(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            module = folder/'staged.ko'
            module.write_bytes(b'changed module')
            cfg = folder/'config.json'
            cfg.write_text(json.dumps({'folder':str(folder),'override':str(folder/'override'),
                'kernel':'6.8.0-138-generic','files':{'mt76.ko':{'source':str(module),'sha256':'0'*64}},'delay_s':0}))
            with patch.object(INSTALL,'rollback',return_value={'restored':True}) as rollback, patch.object(INSTALL,'command') as command:
                INSTALL.guard(cfg)
                rollback.assert_called_once()
                command.assert_not_called()
            result = json.loads((folder/'install_final.json').read_text())
            self.assertFalse(result['confirmed'])
            self.assertIn('changed during installation',result['error'])
            self.assertTrue(result['rollback']['restored'])


if __name__ == '__main__':
    unittest.main()
