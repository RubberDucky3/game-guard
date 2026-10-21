"""Game-aware dispatch gating for explicitly managed background schedules."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parent


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(data, indent=2), encoding='utf-8')
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_json(path, default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def windows_processes():
    result = subprocess.run(['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive', '-Command',
        'Get-Process | Select-Object -ExpandProperty ProcessName | ConvertTo-Json -Compress'],
        capture_output=True, text=True, timeout=15, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise RuntimeError('Windows process enumeration failed')
    data = json.loads(result.stdout)
    return [data] if isinstance(data, str) else data


def canonical_home(config):
    value = config.get('hermes_home')
    if value is None and not config.get('managed_job_ids'):
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError('hermes_home must be explicitly configured for managed jobs')
    home = Path(value).expanduser()
    if not home.is_absolute():
        raise ValueError('hermes_home must expand to an absolute path')
    return home.resolve()


def validate_config(config):
    import re
    if not isinstance(config, dict):
        raise ValueError('Copy config.example.json to config.json first')
    for key in ['game_processes', 'managed_job_ids']:
        values = config.get(key)
        if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
            raise ValueError('Config requires lists of nonempty process names and job IDs')
    if any(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', value) is None for value in config['managed_job_ids']):
        raise ValueError('Invalid managed job ID')
    cooldown = config.get('cooldown_seconds')
    limit = config.get('max_resumes_per_tick', 1)
    if type(cooldown) is not int or cooldown < 0 or type(limit) is not int or limit < 1:
        raise ValueError('Cooldown must be nonnegative; resume limit must be positive')
    canonical_home(config)
    return config


def hermes_callbacks(config):
    """Bind read/write operations to one explicitly configured Hermes home."""
    selected = set(config['managed_job_ids'])
    if not selected:
        return lambda: [], lambda action, job_id: None
    home = canonical_home(config)
    registry = home / 'cron' / 'jobs.json'
    if not registry.is_file():
        raise ValueError('Configured Hermes job registry does not exist')

    def read_jobs():
        data = load_json(registry)
        if not isinstance(data, dict) or not isinstance(data.get('jobs'), list):
            raise ValueError('Unsupported Hermes job registry format')
        return data['jobs']

    def command(action, job_id):
        if action not in ['pause', 'resume'] or job_id not in selected:
            raise ValueError('Unapproved scheduler operation')
        executable = shutil.which('hermes')
        if not executable:
            raise RuntimeError('Hermes CLI not available')
        env = dict(os.environ, HERMES_HOME=str(home))
        env.pop('HERMES_PROFILE', None)
        result = subprocess.run([executable, 'cron', action, job_id], env=env,
            capture_output=True, text=True, timeout=45,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise RuntimeError('Hermes cron command failed')

    return read_jobs, command


def normalize_process(name):
    name = name.strip().lower()
    return name[:-4] if name.endswith('.exe') else name


def detect_games(process_names, config):
    allowed = {normalize_process(n) for n in config['game_processes']}
    return sorted({normalize_process(n) for n in process_names} & allowed)


def transition(previous, blocked, now, cooldown):
    if blocked:
        return {'mode': 'GAMING', 'clear_since': None}
    clear_since = previous.get('clear_since')
    if previous.get('mode') == 'GAMING':
        clear_since = now
    if clear_since is not None and now - clear_since < cooldown:
        return {'mode': 'COOLDOWN', 'clear_since': clear_since}
    return {'mode': 'READY', 'clear_since': None}


def pause_stamp(job):
    # Exclude scheduler-mutated execution counters, but honor human policy edits.
    keys = ['paused_at', 'paused_reason', 'prompt', 'schedule', 'script',
            'monitor', 'skills', 'workdir', 'model', 'provider']
    import hashlib
    content = json.dumps({key: job.get(key) for key in keys}, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def plan_actions(jobs, managed_ids, owned, hold):
    actions = []
    for job in jobs:
        job_id = job['id']
        if job_id not in managed_ids:
            continue
        record = owned.get(job_id)
        if record and (job.get('enabled') or record.get('stamp') != pause_stamp(job)):
            actions.append(('forget', job_id))
            record = None
        if hold and job.get('enabled') and job.get('state') not in ['completed', 'cancelled']:
            actions.append(('pause', job_id))
        elif not hold and record and not job.get('enabled') and job.get('state') == 'paused':
            actions.append(('resume', job_id))
    return actions


def tick(root=ROOT, read_jobs=None, command=None, process_source=windows_processes, now=None):
    now = time.time() if now is None else now
    config = validate_config(load_json(root / 'config.json'))
    if read_jobs is None or command is None:
        configured_read, configured_command = hermes_callbacks(config)
        read_jobs = read_jobs if read_jobs is not None else configured_read
        command = command if command is not None else configured_command
    configured_home = canonical_home(config)
    home = str(configured_home) if configured_home is not None else None
    state_path = root / 'state' / 'state.json'
    state = load_json(state_path, {})
    owned = state.setdefault('owned', {})
    detection_error = None
    try:
        games = detect_games(process_source(), config)
    except Exception as exc:
        games = []
        detection_error = type(exc).__name__
    manual = (root / 'gaming_mode.on').exists()
    state.update(transition(state, bool(games or manual or detection_error), now, config['cooldown_seconds']))
    state.update(games=games, manual=manual, detection_error=detection_error, checked_at=now)
    atomic_json(state_path, state)
    errors, applied = [], []
    resumes = 0
    hold = state['mode'] != 'READY'
    # Keep unverifiable ownership intact for diagnosis/recovery, but never act on it.
    blocked_ids = set()
    for job_id, record in owned.items():
        if record.get('hermes_home') != home or home is None:
            blocked_ids.add(job_id)
            errors.append({'action': 'ownership', 'job_id': job_id,
                           'error': 'SchedulerHomeMismatch' if record.get('hermes_home') else 'UnboundOwnership'})
    managed_ids = [job_id for job_id in config['managed_job_ids'] if job_id not in blocked_ids]
    for action, job_id in plan_actions(read_jobs(), managed_ids, owned, hold):
        if action == 'forget':
            owned.pop(job_id, None)
            atomic_json(state_path, state)
            continue
        if action == 'resume' and resumes >= config.get('max_resumes_per_tick', 1):
            continue
        # Recheck the exact target before any external write.
        current = next((j for j in read_jobs() if j['id'] == job_id), None)
        if current is None:
            continue
        if action == 'pause' and not current.get('enabled'):
            continue
        if action == 'resume' and (current.get('enabled') or pause_stamp(current) != owned[job_id].get('stamp')):
            owned.pop(job_id, None)
            atomic_json(state_path, state)
            continue
        try:
            command(action, job_id)
            after = next(j for j in read_jobs() if j['id'] == job_id)
            if action == 'pause':
                if after.get('enabled') or after.get('state') != 'paused':
                    raise RuntimeError('Pause verification failed')
                owned[job_id] = {'stamp': pause_stamp(after), 'hermes_home': home}
            else:
                if not after.get('enabled'):
                    raise RuntimeError('Resume verification failed')
                owned.pop(job_id, None)
                resumes += 1
            applied.append([action, job_id])
            atomic_json(state_path, state)
        except Exception as exc:
            errors.append({'action': action, 'job_id': job_id, 'error': type(exc).__name__})
    state.update(last_actions=applied, errors=errors)
    atomic_json(state_path, state)
    return state


def check(root=ROOT, process_source=windows_processes, now=None):
    """Fresh read-only dispatch check; stale/missing detector data never permits work."""
    config = validate_config(load_json(root / 'config.json'))
    state = load_json(root / 'state' / 'state.json', {})
    now = time.time() if now is None else now
    try:
        games = detect_games(process_source(), config)
        error = None
    except Exception as exc:
        games, error = [], type(exc).__name__
    manual = (root / 'gaming_mode.on').exists()
    # Stored GAMING/COOLDOWN must be cleared by the tick, not by an ad-hoc launcher.
    blocked = bool(games or manual or error or state.get('mode', 'READY') != 'READY')
    return {'blocked': blocked, 'games': games, 'manual': manual, 'detection_error': error}


@contextmanager
def exclusive(root):
    directory = root / 'state'
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'guard.lock').open('a+b') as handle:
        if handle.tell() == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['tick', 'status', 'check', 'on', 'off'])
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.action in ['status', 'check']:
            result = check(root)
            if args.action == 'status':
                result['last_tick'] = load_json(root / 'state' / 'state.json', {})
            print(json.dumps(result, indent=2))
            return 3 if args.action == 'check' and result['blocked'] else 0
        with exclusive(root):
            marker = root / 'gaming_mode.on'
            if args.action == 'on':
                marker.touch()
            elif args.action == 'off':
                marker.unlink(missing_ok=True)
            previous = load_json(root / 'state' / 'state.json', {})
            state = tick(root)
            changed = previous.get('mode') != state['mode'] or state['last_actions'] or state['errors']
            if args.action != 'tick' or changed:
                print(json.dumps({'mode': state['mode'], 'games': state['games'], 'manual': state['manual'],
                    'actions': state['last_actions'], 'errors': state['errors'], 'detection_error': state['detection_error']}))
            with (root / 'state' / 'events.jsonl').open('a', encoding='utf-8') as handle:
                if changed:
                    handle.write(json.dumps({'at': datetime.now(timezone.utc).isoformat(), 'mode': state['mode'],
                        'actions': state['last_actions'], 'errors': state['errors']}) + '\n')
            return 1 if state['errors'] else 0
    except Exception as exc:
        print(json.dumps({'blocked': True, 'error': type(exc).__name__}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
