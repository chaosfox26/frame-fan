import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class OfflineChecks(unittest.TestCase):
    def test_stock_ownership_requires_successful_unit_inspection(self):
        source = (ROOT / "selftest-root.sh").read_text()
        assertion = next(line for line in source.splitlines() if line.startswith('chk "stock controller owns the service"'))
        helper = re.search(r"^stock_owns_service\(\) \{.*?^\}", source, re.MULTILINE | re.DOTALL)
        script = '\n'.join([
            'U=deckard-fan-control',
            'chk() { shift; "$@"; }',
            'systemctl() { [ "$#" = 2 ] && [ "$1" = cat ] && [ "$2" = deckard-fan-control ] || return 99; printf "%s" "$UNIT_TEXT"; return "$INSPECT_STATUS"; }',
            helper[0] if helper else '',
            assertion,
        ])
        for text, status, passes in [
            ('ExecStart=/usr/share/deckard-fan-control/fancontrol.py --run', 0, True),
            ('ExecStart=/etc/frame-fan/fan/fancontrol.py --run', 0, False),
            ('', 1, False),
            ('ExecStart=/usr/share/deckard-fan-control/fancontrol.py --run', 1, False),
        ]:
            with self.subTest(text=text, status=status):
                result = subprocess.run(
                    ['bash', '-c', script],
                    env={**os.environ, 'UNIT_TEXT': text, 'INSPECT_STATUS': str(status)},
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode == 0, passes, result.stderr)

    def test_extracted_tree_rejects_symlinks_and_hardlinks(self):
        source = (ROOT / "update-helper.sh").read_text()
        assertion = next(line for line in source.splitlines() if '[ -z "$(find "$T/x"' in line)
        for kind, passes in [('directory', True), ('file', True), ('symlink', False), ('hardlink', False)]:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                tree = Path(temp) / 'x'
                tree.mkdir()
                if kind == 'directory':
                    (tree / 'child').mkdir()
                elif kind == 'symlink':
                    (tree / 'child').symlink_to('missing')
                else:
                    (tree / 'child').write_text('ordinary fixture')
                    if kind == 'hardlink':
                        os.link(tree / 'child', tree / 'other')
                result = subprocess.run(
                    ['bash', '-c', assertion],
                    env={**os.environ, 'T': temp},
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode == 0, passes, result.stderr)


if __name__ == '__main__':
    unittest.main()
