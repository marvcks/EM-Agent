import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/em-agent/deploy-image.py'
SPEC = importlib.util.spec_from_file_location('em_agent_deploy', SCRIPT)
deploy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deploy)

OLD_IMAGE = 'sha256:' + 'a' * 64
NEW_IMAGE = 'sha256:' + 'b' * 64
COMMIT = 'c' * 40
COMPOSE = '''name: openhands
services:
  canvas:
    image: ghcr.io/openhands/agent-canvas:1.27.1
    ports:
      - '127.0.0.1:8000:8000'
    volumes:
      - ./frontend:/opt/agent-canvas/frontend:ro
      - ./data:/home/openhands/.openhands
      - ./projects:/projects
    env_file:
      - runtime.env
'''


class DeploymentTests(unittest.TestCase):
    # @spec ER-004 — EditRetro mounts are independent and preserve rollback state.
    def test_editretro_mount_is_independent_and_idempotent(self):
        result = deploy.render_compose(COMPOSE, NEW_IMAGE, editretro_tools=True)
        self.assertIn('/opt/em-agent-tools/editretro:/opt/em-agent-tools/editretro:ro', result)
        self.assertIn('/opt/em-agent-tools/python:/opt/em-agent-tools/python:ro', result)
        self.assertNotIn('/opt/em-agent-tools/aizynthfinder', result)
        self.assertEqual(deploy.render_compose(result, NEW_IMAGE, editretro_tools=True), result)
        self.assertNotIn('/opt/em-agent-tools/editretro', deploy.render_compose(COMPOSE, OLD_IMAGE))
        with self.assertRaises(ValueError):
            deploy.render_compose(COMPOSE.replace('    volumes:\n', '    volumes:\n      - /other:/opt/em-agent-tools/editretro:ro\n'), NEW_IMAGE, editretro_tools=True)

    # @spec MG-004 — Molecular-generation runtime mounts stay independent and rollback-safe.
    def test_molgen_mount_is_independent_and_idempotent(self):
        result = deploy.render_compose(COMPOSE, NEW_IMAGE, molgen_tools=True)
        self.assertIn('/opt/em-agent-tools/molgen:/opt/em-agent-tools/molgen:ro', result)
        self.assertIn('/opt/em-agent-tools/python:/opt/em-agent-tools/python:ro', result)
        self.assertNotIn('/opt/em-agent-tools/editretro', result)
        self.assertEqual(deploy.render_compose(result, NEW_IMAGE, molgen_tools=True), result)
        self.assertNotIn('/opt/em-agent-tools/molgen', deploy.render_compose(COMPOSE, OLD_IMAGE))
        with self.assertRaises(ValueError):
            deploy.render_compose(COMPOSE.replace('    volumes:\n', '    volumes:\n      - /other:/opt/em-agent-tools/molgen:ro\n'), NEW_IMAGE, molgen_tools=True)

    # @spec CNT2D-007 — Independent, read-only conduction runtime; rollback keeps old mounts.
    def test_cnt2d_mount_is_independent_and_idempotent(self):
        result = deploy.render_compose(COMPOSE, NEW_IMAGE, cnt2d_tools=True)
        self.assertIn('/opt/em-agent-tools/cnt2d:/opt/em-agent-tools/cnt2d:ro', result)
        self.assertIn('/opt/em-agent-tools/python:/opt/em-agent-tools/python:ro', result)
        self.assertNotIn('/opt/em-agent-tools/magus', result)
        self.assertEqual(deploy.render_compose(result, NEW_IMAGE, cnt2d_tools=True), result)
        self.assertNotIn('/opt/em-agent-tools/cnt2d', deploy.render_compose(COMPOSE, OLD_IMAGE))

    # @spec AR-004 — Analysis runtime and Claude sessions survive recreation
    def test_analysis_runtime_has_independent_readonly_mount_and_persistent_claude_state(self):
        result = deploy.render_compose(COMPOSE, NEW_IMAGE, analysis_tools=True)
        self.assertIn('/opt/em-agent-tools/analysis:/opt/em-agent-tools/analysis:ro', result)
        self.assertIn('./claude-state:/home/openhands/.claude', result)
        self.assertEqual(deploy.render_compose(result, NEW_IMAGE, analysis_tools=True), result)
        rollback = deploy.render_compose(COMPOSE, OLD_IMAGE, remove_frontend=False)
        self.assertNotIn('/opt/em-agent-tools/analysis:', rollback)
        self.assertIn('./claude-state:/home/openhands/.claude', rollback)
        with self.assertRaises(ValueError):
            deploy.render_compose(COMPOSE.replace('    volumes:\n', '    volumes:\n      - /other:/opt/em-agent-tools/analysis:ro\n'), NEW_IMAGE, analysis_tools=True)

    def test_bde_mounts_are_independent_idempotent_and_preserve_rollback(self):
        result = deploy.render_compose(COMPOSE, NEW_IMAGE, bde_tools=True)
        self.assertIn('/opt/em-agent-tools/bde:/opt/em-agent-tools/bde:ro', result)
        self.assertIn('/opt/em-agent-tools/python:/opt/em-agent-tools/python:ro', result)
        self.assertNotIn('/opt/em-agent-tools/magus', result)
        self.assertEqual(deploy.render_compose(result, NEW_IMAGE, bde_tools=True), result)
        self.assertNotIn('/opt/em-agent-tools/bde', deploy.render_compose(COMPOSE, OLD_IMAGE, remove_frontend=False))
        with self.assertRaises(ValueError):
            deploy.render_compose(COMPOSE.replace('    volumes:\n', '    volumes:\n      - /other:/opt/em-agent-tools/bde:ro\n'), NEW_IMAGE, bde_tools=True)

    # @spec CM-005 — Isolated morphology runtime mounts share the frozen Python
    def test_morphology_mounts_are_independent_idempotent_and_preserve_rollback(self):
        result = deploy.render_compose(COMPOSE, NEW_IMAGE, morphology_tools=True)
        self.assertIn('/opt/em-agent-tools/crystal-morphology:/opt/em-agent-tools/crystal-morphology:ro', result)
        self.assertIn('/opt/em-agent-tools/python:/opt/em-agent-tools/python:ro', result)
        self.assertNotIn('/opt/em-agent-tools/bde', result)
        self.assertEqual(deploy.render_compose(result, NEW_IMAGE, morphology_tools=True), result)
        self.assertNotIn('/opt/em-agent-tools/crystal-morphology', deploy.render_compose(COMPOSE, OLD_IMAGE, remove_frontend=False))
        with self.assertRaises(ValueError):
            deploy.render_compose(COMPOSE.replace('    volumes:\n', '    volumes:\n      - /other:/opt/em-agent-tools/crystal-morphology:ro\n'), NEW_IMAGE, morphology_tools=True)

    def test_reaction_mounts_have_independent_readonly_lifecycle(self):
        result = deploy.render_compose(COMPOSE, NEW_IMAGE, reaction_tools=True)
        for source, destination in deploy.REACTION_MOUNTS.items():
            self.assertIn(f'{source}:{destination}:ro', result)
        self.assertNotIn('/opt/em-agent-tools/magus', result)
        self.assertEqual(deploy.render_compose(result, NEW_IMAGE, reaction_tools=True), result)
        self.assertNotIn('/opt/em-agent-tools/aizynthfinder', deploy.render_compose(COMPOSE, OLD_IMAGE, remove_frontend=False))
        with self.assertRaises(ValueError):
            deploy.render_compose(COMPOSE.replace('    volumes:\n', '    volumes:\n      - /other:/opt/em-agent-tools/python:ro\n'), NEW_IMAGE, reaction_tools=True)

    def test_magus_mounts_are_readonly_idempotent_and_not_added_to_rollback(self):
        result = deploy.render_compose(COMPOSE, NEW_IMAGE, science_tools=True)
        for source, destination in deploy.SCIENCE_MOUNTS.items():
            self.assertIn(f'{source}:{destination}:ro', result)
        self.assertEqual(deploy.render_compose(result, NEW_IMAGE, science_tools=True), result)
        rollback = deploy.render_compose(COMPOSE, OLD_IMAGE, remove_frontend=False)
        self.assertNotIn('/opt/em-agent-tools/magus', rollback)
        with self.assertRaises(ValueError):
            deploy.render_compose(COMPOSE.replace('    volumes:\n', '    volumes:\n      - /other:/opt/em-agent-tools/magus:ro\n'), NEW_IMAGE, science_tools=True)

    def test_image_switch_retains_configuration_and_adds_state_mounts_once(self):
        result = deploy.render_compose(COMPOSE, NEW_IMAGE)
        self.assertIn(f'image: {NEW_IMAGE}', result)
        self.assertNotIn('/opt/agent-canvas/frontend', result)
        self.assertIn("'127.0.0.1:8000:8000'", result)
        self.assertIn('      - runtime.env', result)
        self.assertIn('./data:/home/openhands/.openhands', result)
        for name, destination in deploy.STATE_DIRS.items():
            self.assertIn(f'./{name}:{destination}', result)
        self.assertEqual(deploy.render_compose(result, NEW_IMAGE), result)
        fallback = deploy.render_compose(COMPOSE, OLD_IMAGE, remove_frontend=False)
        self.assertIn('./frontend:/opt/agent-canvas/frontend:ro', fallback)
        self.assertIn('./workspace:/home/openhands/workspace', fallback)

    def test_rejects_mutable_images_and_ambiguous_mount_ownership(self):
        with self.assertRaises(ValueError):
            deploy.render_compose(COMPOSE, 'em-agent:latest')
        with self.assertRaises(ValueError):
            deploy.render_compose(COMPOSE + '    image: other\n', NEW_IMAGE)
        with self.assertRaises(ValueError):
            deploy.render_compose(COMPOSE.replace('    volumes:\n', '    volumes:\n      - /elsewhere:/home/openhands/workspace\n'), NEW_IMAGE)

    def test_file_manifest_preserves_symlinks_without_reading_their_targets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'result.log').write_text('Normal termination\n')
            (root / 'python').symlink_to('/missing/interpreter')
            manifest = deploy.file_manifest(root)
            self.assertEqual(manifest['python'], 'link:/missing/interpreter')
            self.assertEqual(len(manifest['result.log']), 64)

    def test_running_conversation_blocks_restart(self):
        with patch.object(deploy, 'run', return_value=json.dumps([{'id': 'active', 'status': 'running'}])):
            with self.assertRaisesRegex(RuntimeError, 'Conversations are running'):
                deploy.check_idle()

    def test_migrated_home_state_uses_runtime_account_without_following_links(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private = root / 'input.gjf'
            private.write_text('water')
            private.chmod(0o600)
            link = root / 'python'
            link.symlink_to('/outside/python')
            with patch.object(deploy.os, 'chown') as chown:
                deploy.normalize_ownership(root, 10001, 10001)
            self.assertEqual({call.args[0] for call in chown.call_args_list}, {root, private, link})
            for call in chown.call_args_list:
                self.assertEqual(call.args[1:], (10001, 10001))
                self.assertFalse(call.kwargs['follow_symlinks'])
            self.assertEqual(private.stat().st_mode & 0o777, 0o600)

    def test_unhealthy_candidate_automatically_restores_previous_image_and_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'compose.yaml').write_text(COMPOSE)
            (root / 'data').mkdir()
            (root / 'data/session.json').write_text('{"id":"existing"}\n')
            for name in deploy.STATE_DIRS:
                (root / name).mkdir()
            (root / 'workspace/result.log').write_text('Normal termination\n')
            before = deploy.file_manifest(root / 'workspace')
            previous = {
                'Image': OLD_IMAGE,
                'Config': {'Labels': {'org.opencontainers.image.revision': deploy.UPSTREAM_REVISION}},
                'Mounts': [{'Destination': destination, 'Source': str(root / name)} for name, destination in deploy.STATE_DIRS.items()],
            }
            image = {'Id': NEW_IMAGE, 'Config': {'Labels': {
                'org.opencontainers.image.source': deploy.SOURCE,
                'org.opencontainers.image.revision': COMMIT,
                'io.em-agent.upstream.revision': deploy.UPSTREAM_REVISION,
            }}}
            starts = []

            def docker(*args, input=None):
                if args[:3] == ('docker', 'image', 'inspect'):
                    return json.dumps([image])
                if args[:2] == ('docker', 'inspect'):
                    return json.dumps([previous])
                if args[:3] == ('docker', 'exec', 'openhands'):
                    if 'os.getuid()' in args[-1]:
                        return json.dumps({'uid': 10001, 'gid': 10001})
                    return json.dumps([{'id': 'existing', 'status': 'finished'}])
                if args[:3] == ('docker', 'exec', '-i'):
                    self.assertEqual(json.loads(input), before)
                    return json.dumps({'checked': 1, 'mismatches': []})
                if args[:2] == ('docker', 'compose') and 'up' in args:
                    starts.append((root / 'compose.yaml').read_text())
                return ''

            with patch.object(deploy, 'run', side_effect=docker), patch.object(deploy, 'wait_healthy', side_effect=[RuntimeError('unhealthy'), None]), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, 'unhealthy'):
                    deploy.deploy(root, 'em-agent:' + COMMIT, COMMIT)
            self.assertEqual(len(starts), 2)
            self.assertIn(NEW_IMAGE, starts[0])
            self.assertIn(OLD_IMAGE, starts[1])
            self.assertIn('./workspace:/home/openhands/workspace', starts[1])
            self.assertEqual(deploy.file_manifest(root / 'workspace'), before)
            self.assertEqual((root / 'data/session.json').read_text(), '{"id":"existing"}\n')


if __name__ == '__main__':
    unittest.main()
