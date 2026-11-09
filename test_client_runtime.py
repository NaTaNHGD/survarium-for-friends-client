from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from client_runtime import runtime_command, validate_client


class ClientRuntimeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is used only for the development policy test')
    def test_animation_capacity_boundary(self) -> None:
        script = """
const assert = require('node:assert/strict');
const {deferTransition} = require('./animation_guard.js');
assert.equal(deferTransition(1024, 0xb780, false), false);
assert.equal(deferTransition(1024, 0xb781, false), true);
assert.equal(deferTransition(1024, 0xc000, true), false);
const {preserveSmallStep, compatibleCapsule} = require('./movement_guard.js');
assert.equal(preserveSmallStep(1, .004, .01), true);
assert.equal(preserveSmallStep(9, .009, .01), true);
assert.equal(preserveSmallStep(0, .004, .01), false);
assert.equal(preserveSmallStep(10, .004, .01), false);
assert.equal(preserveSmallStep(1, .01, .01), false);
assert.equal(preserveSmallStep(1, NaN, .01), false);
assert.equal(compatibleCapsule(.76, .76, 1.8, 1.1), true);
assert.equal(compatibleCapsule(.35, .35, 1.8, 1.1), false);
assert.equal(compatibleCapsule(.76, .76, 2.5, 1.1), false);
for (const current of [0, -1, 0xb801, NaN, '1024'])
  assert.equal(deferTransition(current, 0xc000, false), false);
for (const requested of [-1, NaN, '50000'])
  assert.equal(deferTransition(1024, requested, false), false);
"""
        result = subprocess.run(['node', '-e', script], cwd=Path(__file__).parent,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_runtime_preserves_paths_and_refuses_unverified_binary(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            game = Path(folder) / 'Steam Game'
            executable = game / 'binaries/x64/survarium.exe'
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b'unverified test executable')
            command = runtime_command(game, '192.168.1.2', Path(folder) / 'Client Data')
            self.assertEqual(command[2:], ['--game', str(game.resolve()), '--host', '192.168.1.2',
                                         '--data', str((Path(folder) / 'Client Data').resolve())])
            with self.assertRaises(ValueError):
                validate_client(executable)

