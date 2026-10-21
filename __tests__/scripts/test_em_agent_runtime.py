import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('em_agent_runtime', ROOT / 'tools/em_agent_runtime/runtime.py')


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = importlib.util.module_from_spec(SPEC)
        SPEC.loader.exec_module(cls.runtime)

    # @spec AR-002 — Enabled native skills, without taking over user content
    def test_native_skill_sync_tracks_preferences_and_preserves_foreign_skills(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            source = home / '.openhands/skills'
            for name in ['mineru', 'bde', 'custom']:
                (source / name).mkdir(parents=True)
                (source / name / 'SKILL.md').write_text(f'---\nname: {name}\ndescription: Test skill\n---\nUse this skill.\n')
            destination = home / '.claude/skills'
            (destination / 'custom').mkdir(parents=True)
            original = destination / 'custom/SKILL.md'
            original.write_text('Native user skill')
            settings = home / '.openhands/settings.json'
            settings.write_text(json.dumps({'misc_settings': {'app_preferences': {'disabled_skills': ['bde']}}}))

            self.runtime.sync_claude_skills(home)
            self.assertTrue((destination / 'mineru/SKILL.md').is_file())
            self.assertFalse((destination / 'bde').exists())
            self.assertEqual(original.read_text(), 'Native user skill')

            settings.write_text(json.dumps({'misc_settings': {'app_preferences': {'disabled_skills': ['mineru']}}}))
            self.runtime.sync_claude_skills(home)
            self.runtime.sync_claude_skills(home)
            self.assertFalse((destination / 'mineru').is_symlink())
            self.assertTrue((destination / 'bde/SKILL.md').is_file())
            self.assertEqual(original.read_text(), 'Native user skill')

            # A user replacing a previously managed link owns the replacement.
            (destination / 'bde').unlink()
            (destination / 'bde').mkdir()
            (destination / 'bde/SKILL.md').write_text('User replacement')
            settings.write_text(json.dumps({'misc_settings': {'app_preferences': {'disabled_skills': ['bde']}}}))
            self.runtime.sync_claude_skills(home)
            self.assertEqual((destination / 'bde/SKILL.md').read_text(), 'User replacement')

    # @spec AR-002 — Missing sources and invalid settings cannot expose skills
    def test_removed_sources_are_pruned_and_invalid_preferences_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            source = home / '.openhands/skills/mineru'
            source.mkdir(parents=True)
            (source / 'SKILL.md').write_text('---\nname: mineru\ndescription: Test\n---\n')
            self.runtime.sync_claude_skills(home)
            (source / 'SKILL.md').unlink()
            self.runtime.sync_claude_skills(home)
            self.assertFalse((home / '.claude/skills/mineru').is_symlink())
            (home / '.openhands/settings.json').write_text('{invalid')
            with self.assertRaises(ValueError):
                self.runtime.sync_claude_skills(home)

    # @spec AR-002 — ACP provider data-directory isolation is retained
    def test_native_skill_sync_uses_the_provider_config_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            skill = home / '.openhands/skills/mineru'
            skill.mkdir(parents=True)
            (skill / 'SKILL.md').write_text('---\nname: mineru\ndescription: Test\n---\n')
            isolated = home / 'isolated-claude'
            with patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': str(isolated)}):
                self.runtime.sync_claude_skills(home)
            self.assertTrue((isolated / 'skills/mineru/SKILL.md').is_file())
            self.assertFalse((home / '.claude/skills/mineru').exists())

    # @spec AR-001 — Task-only default with explicit project override
    def test_task_shell_selects_analysis_python_and_keeps_project_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            analysis = root / 'analysis'
            project = root / 'project'
            for directory, label in [(analysis, 'analysis'), (project, 'project')]:
                (directory / 'bin').mkdir(parents=True)
                python = directory / 'bin/python'
                python.write_text(f'#!/bin/sh\necho {label}\n')
                python.chmod(0o755)
            env = {**os.environ, 'EM_AGENT_ANALYSIS_ENV': str(analysis)}
            env.pop('VIRTUAL_ENV', None)
            script = ROOT / 'tools/em_agent_runtime/task-shell.sh'
            command = f'. "{script}"; python; . "{script}"; printf "%s" "$PATH"'
            result = subprocess.run(['/bin/bash', '-c', command], env=env, capture_output=True, text=True, check=True)
            self.assertTrue(result.stdout.startswith('analysis\n'))
            self.assertEqual(result.stdout.count(str(analysis / 'bin')), 1)
            env.update(VIRTUAL_ENV=str(project), PATH=f'{project}/bin:{os.environ["PATH"]}')
            result = subprocess.run(['/bin/bash', '-c', f'. "{script}"; python'], env=env, capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout.strip(), 'project')

    # @spec AR-001 — ACP terminals may use sh and ignore BASH_ENV
    def test_acp_launcher_passes_analysis_to_non_bash_children(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = root / 'runtime'
            runtime.mkdir()
            (runtime / 'runtime.py').write_text('pass\n')
            (runtime / 'task-shell.sh').write_text((ROOT / 'tools/em_agent_runtime/task-shell.sh').read_text())
            analysis = root / 'analysis'
            (analysis / 'bin').mkdir(parents=True)
            python = analysis / 'bin/python'
            python.write_text('#!/bin/sh\necho analysis\n')
            python.chmod(0o755)
            upstream = root / 'upstream'
            upstream.write_text('#!/bin/sh\npython; printf "%s" "$1"\n')
            upstream.chmod(0o755)
            launcher = root / 'launcher'
            source = (ROOT / 'tools/em_agent_runtime/claude-agent-acp').read_text()
            source = source.replace('/opt/agent-canvas/em_agent_runtime', str(runtime))
            source = source.replace('/usr/local/bin/python', sys.executable)
            source = source.replace('/usr/local/bin/claude-agent-acp.upstream', str(upstream))
            launcher.write_text(source)
            env = {**os.environ, 'EM_AGENT_ANALYSIS_ENV': str(analysis)}
            env.pop('VIRTUAL_ENV', None)
            result = subprocess.run(['/bin/sh', str(launcher), 'forwarded-argument'], env=env,
                                    capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout, 'analysis\nforwarded-argument')


if __name__ == '__main__':
    unittest.main()
