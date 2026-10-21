import unittest
import json
import tempfile
from pathlib import Path
import gaming_guard as g


class DetectorTests(unittest.TestCase):
    def test_process_adapter_only_enumerates_process_names(self):
        from unittest.mock import Mock, patch
        with patch.object(g.subprocess, 'run', return_value=Mock(returncode=0, stdout='["cs2","worker"]')) as run:
            self.assertEqual(g.windows_processes(), ['cs2', 'worker'])
        self.assertEqual(run.call_args.args[0], ['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive', '-Command',
                         'Get-Process | Select-Object -ExpandProperty ProcessName | ConvertTo-Json -Compress'])
        self.assertEqual(run.call_count, 1)

    def test_exact_game_name_not_launcher_or_substring(self):
        config = {'game_processes': ['cs2', 'FortniteClient-Win64-Shipping.exe']}
        self.assertEqual(g.detect_games(['steam', 'mycs2helper', 'CS2.exe'], config), ['cs2'])
        self.assertEqual(g.detect_games(['epicgameslauncher', 'javaw', 'steam'], config), [])
        self.assertEqual(g.detect_games(['FortniteClient-Win64-Shipping'], config), ['fortniteclient-win64-shipping'])


    def test_clear_period_before_resume_and_reentry(self):
        state = g.transition({}, True, 100, 120)
        self.assertEqual(state['mode'], 'GAMING')
        state = g.transition(state, False, 110, 120)
        self.assertEqual(state['mode'], 'COOLDOWN')
        state = g.transition(state, False, 229, 120)
        self.assertEqual(state['mode'], 'COOLDOWN')
        self.assertEqual(g.transition(state, False, 230, 120)['mode'], 'READY')
        self.assertEqual(g.transition(state, True, 230, 120)['clear_since'], None)
        self.assertEqual(g.transition({}, False, 100, 120)['mode'], 'READY')


    def test_pause_stamp_does_not_store_private_prompt_text(self):
        stamp = g.pause_stamp({'id': 'example-job', 'prompt': 'private fixture content'})
        self.assertIsInstance(stamp, str)
        self.assertNotIn('private fixture content', stamp)
        self.assertEqual(len(stamp), 64)

    def test_only_allowlisted_enabled_jobs_are_paused(self):
        jobs = [{'id': 'build', 'enabled': True, 'state': 'scheduled'},
                {'id': 'disabled', 'enabled': False, 'state': 'paused'},
                {'id': 'reminder', 'enabled': True, 'state': 'scheduled'}]
        self.assertEqual(g.plan_actions(jobs, ['build', 'disabled'], {}, True), [('pause', 'build')])

    def test_resume_requires_matching_owned_pause(self):
        job = {'id': 'build', 'enabled': False, 'state': 'paused', 'paused_at': 'guard-time'}
        owned = {'build': {'stamp': g.pause_stamp(job)}}
        self.assertEqual(g.plan_actions([job], ['build'], owned, False), [('resume', 'build')])
        job['paused_at'] = 'later-human-time'
        self.assertEqual(g.plan_actions([job], ['build'], owned, False), [('forget', 'build')])
        self.assertEqual(g.plan_actions([job], ['build'], {}, False), [])


class TickTests(unittest.TestCase):
    def test_legacy_unbound_ownership_is_preserved_but_never_adopted(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = {'game_processes': ['cs2'], 'managed_job_ids': ['build'],
                      'cooldown_seconds': 0, 'hermes_home': str(root / 'home')}
            g.atomic_json(root / 'config.json', config)
            job = {'id': 'build', 'enabled': False, 'state': 'paused', 'paused_at': 'legacy'}
            owned = {'build': {'stamp': g.pause_stamp(job)}}
            g.atomic_json(root / 'state/state.json', {'owned': owned})
            command = Mock()
            result = g.tick(root, lambda: [job], command, lambda: [], now=100)
            command.assert_not_called()
            self.assertEqual(result['owned'], owned)
            self.assertEqual(result['errors'][0]['error'], 'UnboundOwnership')
            # Even an enabled copy during gaming must not overwrite old evidence.
            job['enabled'] = True
            result = g.tick(root, lambda: [job], command, lambda: ['cs2'], now=101)
            command.assert_not_called()
            self.assertEqual(result['owned'], owned)

    def test_real_adapter_refuses_resume_against_copied_registry(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job = {'id': 'build', 'enabled': False, 'state': 'paused', 'paused_at': 'same'}
            copied = root / 'copy'
            g.atomic_json(copied / 'cron/jobs.json', {'jobs': [job]})
            g.atomic_json(root / 'config.json', {'game_processes': [], 'managed_job_ids': ['build'],
                          'cooldown_seconds': 0, 'hermes_home': str(copied)})
            owned = {'build': {'stamp': g.pause_stamp(job), 'hermes_home': str((root / 'original').resolve())}}
            g.atomic_json(root / 'state/state.json', {'owned': owned})
            with patch.object(g.subprocess, 'run') as run:
                result = g.tick(root, process_source=lambda: [], now=100)
            run.assert_not_called()
            self.assertEqual(result['owned'], owned)
            self.assertEqual(result['errors'][0]['error'], 'SchedulerHomeMismatch')

    def test_copied_profile_cannot_restore_owned_pause(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = {'game_processes': ['cs2'], 'managed_job_ids': ['build'],
                      'cooldown_seconds': 0, 'hermes_home': str(root / 'original')}
            g.atomic_json(root / 'config.json', config)
            jobs = [{'id': 'build', 'enabled': True, 'state': 'scheduled'}]
            calls = []
            def command(action, job_id):
                calls.append((action, job_id))
                jobs[0].update(enabled=action == 'resume',
                               state='scheduled' if action == 'resume' else 'paused',
                               paused_at='same-metadata')
            g.tick(root, lambda: jobs, command, lambda: ['cs2'], now=100)
            saved = g.load_json(root / 'state/state.json')['owned']
            config['hermes_home'] = str(root / 'copied')
            g.atomic_json(root / 'config.json', config)
            result = g.tick(root, lambda: jobs, command, lambda: [], now=101)
            self.assertEqual(calls, [('pause', 'build')])
            self.assertFalse(jobs[0]['enabled'])
            self.assertEqual(result['owned'], saved)
            self.assertTrue(result['errors'])
            self.assertEqual(saved['build']['hermes_home'], str((root / 'original').resolve()))
            config['hermes_home'] = str(root / 'original' / '..' / 'original')
            g.atomic_json(root / 'config.json', config)
            g.tick(root, lambda: jobs, command, lambda: [], now=102)
            self.assertEqual(calls[-1], ('resume', 'build'))

    def test_pause_persist_cooldown_restore_without_touching_reminder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'config.json').write_text(json.dumps({'game_processes': ['cs2'], 'managed_job_ids': ['build'], 'cooldown_seconds': 120, 'hermes_home': str(root / 'home')}), encoding='utf-8')
            jobs = [{'id': 'build', 'enabled': True, 'state': 'scheduled'},
                    {'id': 'reminder', 'enabled': True, 'state': 'scheduled'}]
            calls = []
            def command(action, job_id):
                calls.append((action, job_id))
                job = next(j for j in jobs if j['id'] == job_id)
                job.update(enabled=action == 'resume', state='scheduled' if action == 'resume' else 'paused', paused_at='test-pause' if action == 'pause' else None)
            result = g.tick(root, lambda: jobs, command, lambda: ['cs2'], now=100)
            self.assertEqual(result['mode'], 'GAMING')
            self.assertEqual(calls, [('pause', 'build')])
            self.assertTrue(jobs[1]['enabled'])
            self.assertIn('build', json.loads((root / 'state/state.json').read_text())['owned'])
            self.assertEqual(g.tick(root, lambda: jobs, command, lambda: [], now=110)['mode'], 'COOLDOWN')
            self.assertEqual(g.tick(root, lambda: jobs, command, lambda: [], now=230)['mode'], 'READY')
            self.assertEqual(calls, [('pause', 'build'), ('resume', 'build')])
            self.assertEqual(json.loads((root / 'state/state.json').read_text())['owned'], {})


class AdapterTests(unittest.TestCase):
    def test_explicit_home_required_only_for_selected_jobs(self):
        read_jobs, command = g.hermes_callbacks({'managed_job_ids': []})
        self.assertEqual(read_jobs(), [])
        with self.assertRaises(ValueError):
            g.hermes_callbacks({'managed_job_ids': ['example-job']})

    def test_cli_target_is_canonical_cwd_independent_and_profile_scoped(self):
        import os
        from unittest.mock import Mock, patch
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / 'home'
            g.atomic_json(home / 'cron/jobs.json', {'jobs': [{'id': 'build'}]})
            config = {'managed_job_ids': ['build'], 'hermes_home': str(home / '..' / 'home')}
            read_jobs, command = g.hermes_callbacks(config)
            previous = Path.cwd()
            try:
                os.chdir(root.parent)
                with patch.dict(os.environ, {'HERMES_HOME': 'wrong-home', 'HERMES_PROFILE': 'wrong-profile'}), \
                     patch.object(g.shutil, 'which', return_value='mock-hermes'), \
                     patch.object(g.subprocess, 'run', return_value=Mock(returncode=0)) as run:
                    self.assertEqual(read_jobs(), [{'id': 'build'}])
                    command('pause', 'build')
                    command('resume', 'build')
                    for call, action in zip(run.call_args_list, ['pause', 'resume']):
                        self.assertEqual(call.args[0], ['mock-hermes', 'cron', action, 'build'])
                        self.assertEqual(call.kwargs['env']['HERMES_HOME'], str(home.resolve()))
                        self.assertNotIn('HERMES_PROFILE', call.kwargs['env'])
                    self.assertEqual(os.environ['HERMES_HOME'], 'wrong-home')
                    self.assertEqual(os.environ['HERMES_PROFILE'], 'wrong-profile')
                    with self.assertRaises(ValueError):
                        command('resume', 'unmanaged')
                    with self.assertRaises(ValueError):
                        command('kill', 'build')
                    self.assertEqual(run.call_count, 2)
            finally:
                os.chdir(previous)

    def test_home_adapter_reads_only_configured_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / 'cron').mkdir()
            (home / 'cron/jobs.json').write_text(json.dumps({'jobs': [{'id': 'example-job', 'enabled': True}]}))
            read_jobs, command = g.hermes_callbacks({'managed_job_ids': ['example-job'], 'hermes_home': str(home)})
            self.assertEqual(read_jobs()[0]['id'], 'example-job')


class ConfigTests(unittest.TestCase):
    def test_rejects_relative_home_before_cwd_can_select_scheduler(self):
        import os
        from unittest.mock import patch
        good = {'game_processes': [], 'managed_job_ids': ['build'], 'cooldown_seconds': 0}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            g.atomic_json(root / 'relative/cron/jobs.json', {'jobs': []})
            previous = Path.cwd()
            try:
                os.chdir(root)
                for home in ['relative', '.', '', 'C:relative', chr(92) + 'relative']:
                    with self.subTest(home=home), self.assertRaises(ValueError):
                        g.validate_config(dict(good, hermes_home=home))
                with self.assertRaises(ValueError):
                    g.hermes_callbacks(dict(good, hermes_home='relative'))
                g.atomic_json(root / 'config.json', dict(good, hermes_home='relative'))
                with self.assertRaises(ValueError):
                    g.tick(root, lambda: [], lambda *args: self.fail('Unexpected write'), lambda: [])
                self.assertEqual(g.canonical_home(dict(good, hermes_home='~/guard-test')),
                                 (Path.home() / 'guard-test').resolve())
            finally:
                os.chdir(previous)

    def test_shipped_example_is_safe_without_a_scheduler(self):
        config = json.loads((g.ROOT / 'config.example.json').read_text(encoding='utf-8'))
        self.assertEqual(g.validate_config(config)['managed_job_ids'], [])
        read_jobs, _ = g.hermes_callbacks(config)
        self.assertEqual(read_jobs(), [])

    def test_rejects_unsafe_or_malformed_config(self):
        good = {'game_processes': ['cs2'], 'managed_job_ids': [], 'cooldown_seconds': 120}
        self.assertEqual(g.validate_config(good), good)
        for changes in [{'managed_job_ids': ['--help']}, {'game_processes': 'cs2'},
                        {'cooldown_seconds': -1}, {'max_resumes_per_tick': 0}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                g.validate_config(dict(good, **changes))


class CliTests(unittest.TestCase):
    @unittest.skipUnless(__import__('os').name == 'nt', 'Native process discovery requires Windows')
    def test_manual_mode_cli_with_no_managed_jobs(self):
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'config.json').write_text(json.dumps({'game_processes': [], 'managed_job_ids': [], 'cooldown_seconds': 0}))
            def call(action):
                return subprocess.run([sys.executable, str(g.ROOT / 'gaming_guard.py'), action, '--root', str(root)],
                                      capture_output=True, text=True, timeout=25)
            self.assertEqual(call('on').returncode, 0)
            self.assertEqual(call('check').returncode, 3)
            self.assertEqual(call('off').returncode, 0)
            self.assertEqual(call('check').returncode, 0)


if __name__ == '__main__':
    unittest.main()
