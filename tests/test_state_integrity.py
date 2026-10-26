import ast
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
REQUEST = {'floor': 60, 'ceil': 98, 't0': 30, 't1': 75, 's': 0}
YAML = 'fan_min_speed: 0\nfan_charging_min_speed: 0\nfan_max_speed: 0\nfan_hysteresis: 0\n  type: ffquad\n  T_threshold: 45\n'


class ApplyFixture:
    def __init__(self):
        tree = ast.parse((ROOT / 'fan-apply.py').read_text())
        names = {'go_stock', 'invalidate_stamp', 'sub', 'interp', 'valid_points', 'parse'}
        definitions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        start = next(i for i, n in enumerate(tree.body) if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Tuple))
        self.tail = compile(ast.Module(body=tree.body[start:], type_ignores=[]), 'apply-fixture', 'exec')
        self.files = {'yaml': YAML}
        self.events = []
        self.now = 1000.0
        self.request = REQUEST
        self.fail_patch = False
        self.ns = {
            'json': json, 're': re, 'sys': SimpleNamespace(stderr=io.StringIO()),
            'STAMP': 'stamp', 'APPLIED': 'applied', 'STOCK': 'yaml', 'CONTROL': 'control',
            'CONFIG': 'config', 'DROPIN': 'dropin', 'UNIT': 'unit',
            'time': SimpleNamespace(time=lambda: self.now, sleep=self.sleep),
            'read_request': lambda: self.request, 'open': self.open, 'write': self.write,
            'patched': self.patched, 'restart': lambda: self.events.append(('restart',)),
            'max_fan': lambda: True, 'sc': lambda *a, **k: self.events.append(('service', *a)),
            'os': SimpleNamespace(
                path=SimpleNamespace(exists=lambda p: p in self.files, dirname=lambda p: 'inert'),
                remove=self.remove, unlink=self.remove, makedirs=lambda *a, **k: None,
            ),
        }
        exec(compile(ast.Module(body=definitions, type_ignores=[]), 'apply-definitions', 'exec'), self.ns)

    def open(self, name):
        if name not in self.files:
            raise FileNotFoundError(name)
        return io.StringIO(self.files[name])

    def write(self, name, text, mode=0o644):
        self.events.append(('write', name))
        self.files[name] = text

    def remove(self, name):
        self.events.append(('remove', name))
        if name not in self.files:
            raise FileNotFoundError(name)
        del self.files[name]

    def sleep(self, seconds):
        self.events.append(('wait', seconds))
        self.now += seconds

    def patched(self):
        if self.fail_patch:
            raise ValueError('inert patch failure')
        return 'inert controller'

    def apply(self, request):
        self.request = request
        self.events.clear()
        try:
            exec(self.tail, self.ns)
        except SystemExit as error:
            if error.code != 0:
                raise


def shell_function(source, name):
    match = re.search(r'^' + name + r'\(\) \{.*?^\}', source, re.MULTILINE | re.DOTALL)
    return match[0] if match else ''


class ShellFixture:
    def __init__(self, base):
        self.base = Path(base)
        self.state = self.base / 'state'
        self.backup = self.state / 'backup'
        self.backup.mkdir(parents=True)
        self.stamp = self.base / 'stamp'
        self.stamp.write_text('1000.000000 stale-request')
        self.events = self.base / 'events'
        self.events.write_text('')
        self.etc = self.base / 'etc'
        (self.etc / 'fan').mkdir(parents=True)
        self.units = self.base / 'units'
        self.units.mkdir()
        self.config = self.base / 'config'
        self.config.mkdir()
        self.sudoers = self.base / 'sudoers'
        self.sudoers.mkdir()
        (self.etc / 'root-lib.sh').write_text('ff_activate() { apply_fixture; }\n')
        self.helper = (ROOT / 'update-helper.sh').read_text()

    def mapped(self, source):
        for old, new in [
            ('/usr/bin/python3 /etc/frame-fan/fan-apply.py', 'apply_fixture'),
            ('/home/steamos/.config/frame-fan', str(self.config)),
            ('/etc/systemd/system', str(self.units)),
            ('/etc/sudoers.d', str(self.sudoers)),
            ('/etc/frame-fan', str(self.etc)),
            ('/run/frame-fan.stamp', str(self.stamp)),
        ]:
            source = source.replace(old, new)
        return source

    def run(self, body):
        names = ['backup_digest', 'backup_ok', 'restore', 'stock', 'do_rollback']
        definitions = '\n'.join(shell_function(self.helper, name) for name in names)
        script = '\n'.join([
            'set -e',
            'systemctl_fixture() { printf "service:%s\\n" "$*" >> "$EVENTS"; }',
            'systemctl() { systemctl_fixture "$@"; }',
            'sleep() { :; }',
            'rm() { printf "remove:%s\\n" "$*" >> "$EVENTS"; for p in "$@"; do if [ "$p" = "$STAMP_FIXTURE" ]; then /bin/rm -f -- "$p"; fi; done; }',
            'tar_fixture() { case "$1" in -xPpf) printf "extract\\n" >> "$EVENTS";; *) /usr/bin/tar "$@";; esac; }',
            'apply_fixture() { [ ! -e "$STAMP_FIXTURE" ] || return 75; printf "apply\\n" >> "$EVENTS"; }',
            'paths() { printf "%s\\n" "$ETC"; }',
            'ff_put() { :; }; ff_sudoers() { :; }; cp() { :; }; chown() { :; }; chmod() { :; }; rmdir() { :; }',
            'sync_fixture() { :; }',
            self.mapped(definitions),
            self.mapped(body),
        ])
        return subprocess.run(['bash', '-c', script], env={
            **os.environ, 'EVENTS': str(self.events), 'STAMP_FIXTURE': str(self.stamp),
            'STATE': str(self.state), 'ETC': str(self.etc), 'UNITDIR': str(self.units),
            'DROPIN': str(self.units / 'dropin'), 'SUDOERS': str(self.sudoers / 'fan'),
            'TAR': 'tar_fixture', 'PY': sys.executable, 'SYSTEMCTL': 'systemctl_fixture', 'SYNC': 'sync_fixture',
        }, capture_output=True, text=True, check=False)

    def archive(self):
        payload = b'good-payload'
        with tarfile.open(self.backup / 'files.tar', 'w', format=tarfile.USTAR_FORMAT) as archive:
            entry = tarfile.TarInfo('fixture.txt')
            entry.size = len(payload)
            archive.addfile(entry, io.BytesIO(payload))
        result = subprocess.run(['/usr/bin/tar', '-tPf', str(self.backup / 'files.tar')], capture_output=True, check=True)
        (self.backup / 'members').write_bytes(result.stdout)
        (self.backup / 'sha256').write_text(hashlib.sha256((self.backup / 'files.tar').read_bytes()).hexdigest() + '\n')


class StateIntegrity(unittest.TestCase):
    def test_duplicate_request_skips_only_while_its_custom_state_remains(self):
        fixture = ApplyFixture()
        fixture.apply(REQUEST)
        self.assertLess(fixture.events.index(('restart',)), fixture.events.index(('write', 'stamp')))
        stamp = fixture.files['stamp']
        fixture.now = 1001
        fixture.apply(REQUEST)
        self.assertEqual(fixture.events, [])
        self.assertEqual(fixture.files['stamp'], stamp)

    def test_stock_then_same_custom_request_reapplies_within_five_seconds(self):
        fixture = ApplyFixture()
        fixture.apply(REQUEST)
        fixture.now = 1000.1
        fixture.apply({'stock': True})
        self.assertEqual(json.loads(fixture.files['applied']), {'stock': True})
        fixture.now = 1003.1
        fixture.apply(REQUEST)
        self.assertEqual(json.loads(fixture.files['applied']), REQUEST)
        self.assertIn(('restart',), fixture.events)

    def test_failed_changed_request_then_prior_request_retries_after_fallback(self):
        fixture = ApplyFixture()
        fixture.apply(REQUEST)
        fixture.now = 1002
        fixture.fail_patch = True
        fixture.apply({**REQUEST, 'floor': 61})
        self.assertEqual(json.loads(fixture.files['applied']), {'stock': True, 'fallback': True})
        self.assertNotIn(('write', 'stamp'), fixture.events)
        fixture.now = 1003.1
        fixture.fail_patch = False
        fixture.apply(REQUEST)
        self.assertEqual(json.loads(fixture.files['applied']), REQUEST)
        self.assertIn(('restart',), fixture.events)

    def test_direct_stock_and_activation_discard_stale_stamp(self):
        library = (ROOT / 'root-lib.sh').read_text()
        uninstall = (ROOT / 'uninstall-root.sh').read_text()
        uninstall = uninstall[uninstall.index('\nD=') + 1:]
        for transition in ['stock', 'activate-saved', 'activate-stock', 'install', 'uninstall']:
            with self.subTest(transition=transition), tempfile.TemporaryDirectory() as temp:
                fixture = ShellFixture(temp)
                if transition in ['activate-saved', 'install']:
                    (fixture.config / 'fan.json').write_text('{}')
                if transition == 'stock':
                    body = 'stock'
                elif transition == 'uninstall':
                    body = uninstall
                else:
                    body = shell_function(library, 'ff_activate')
                    if transition == 'install':
                        body += '\n' + shell_function(library, 'ff_install') + '\nff_install inert-source'
                    else:
                        body += '\nff_activate'
                result = fixture.run(body)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(fixture.stamp.exists())
                events = fixture.events.read_text().splitlines()
                stamp_event = next(i for i, e in enumerate(events) if str(fixture.stamp) in e)
                if transition == 'install':
                    discard = next(i for i, e in enumerate(events) if 'frame-fan.conf' in e)
                    self.assertLess(stamp_event, discard)

    def test_restore_discards_stamp_before_reactivating_old_library(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = ShellFixture(temp)
            fixture.archive()
            result = fixture.run('restore')
            self.assertEqual(result.returncode, 0, result.stderr)
            events = fixture.events.read_text().splitlines()
            self.assertIn('apply', events)
            self.assertFalse(fixture.stamp.exists())

    def test_backup_creation_stores_digest_of_completed_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = ShellFixture(temp)
            (fixture.state / 'backup.new').mkdir()
            start = fixture.helper.index('  paths > "$STATE/backup.new/list"')
            end = fixture.helper.index('  rm -rf "$STATE/backup"', start)
            result = fixture.run('create_fixture() {\n' + fixture.helper[start:end] + '\n}\ncreate_fixture')
            self.assertEqual(result.returncode, 0, result.stderr)
            backup = fixture.state / 'backup.new'
            self.assertTrue((backup / 'sha256').is_file())
            self.assertEqual((backup / 'sha256').read_text().strip(), hashlib.sha256((backup / 'files.tar').read_bytes()).hexdigest())

    def test_invalid_backup_refuses_before_any_live_deletion(self):
        for corruption in ['missing-archive', 'missing-digest', 'wrong-digest', 'truncated', 'truncated-rehashed', 'payload', 'members', 'missing-members']:
            for action in ['restore', 'do_rollback']:
                with self.subTest(corruption=corruption, action=action), tempfile.TemporaryDirectory() as temp:
                    fixture = ShellFixture(temp)
                    fixture.archive()
                    archive = fixture.backup / 'files.tar'
                    if corruption == 'missing-archive':
                        archive.unlink()
                    elif corruption == 'missing-digest':
                        (fixture.backup / 'sha256').unlink()
                    elif corruption == 'wrong-digest':
                        (fixture.backup / 'sha256').write_text('0' * 64 + '\n')
                    elif corruption in ['truncated', 'truncated-rehashed']:
                        archive.write_bytes(archive.read_bytes()[:516])
                        if corruption == 'truncated-rehashed':
                            (fixture.backup / 'sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '\n')
                    elif corruption == 'payload':
                        data = bytearray(archive.read_bytes())
                        data[512:524] = b'evil-payload'
                        archive.write_bytes(data)
                        listing = subprocess.run(['/usr/bin/tar', '-tPf', str(archive)], capture_output=True, check=True)
                        self.assertEqual(listing.stdout, (fixture.backup / 'members').read_bytes())
                    elif corruption == 'members':
                        (fixture.backup / 'members').write_text('other-name\n')
                    else:
                        (fixture.backup / 'members').unlink()
                    result = fixture.run(action)
                    self.assertNotEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(fixture.events.read_text(), '')
                    self.assertTrue(fixture.stamp.exists())


if __name__ == '__main__':
    unittest.main()
