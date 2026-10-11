"""Host socket inventory and explicitly configured service controls."""
import hmac
import json
import os
import re
import subprocess
import threading
from pathlib import Path

_LOCK = threading.Lock()


def command(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=12, check=False)
    if result.returncode:
        raise RuntimeError((result.stderr.strip() or result.stdout.strip() or 'Command failed')[:300])
    return result.stdout


def configured_services():
    path = os.getenv('PORT_SERVICES_FILE', str(Path(__file__).resolve().parents[1] / 'port_services.json'))
    if not Path(path).exists():
        return []
    try:
        services = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except json.JSONDecodeError as exc:
        raise ValueError(f'Service configuration {path} is invalid JSON at line {exc.lineno}, column {exc.colno}. Use a JSON array as shown in port_services.example.json.') from exc
    if not isinstance(services, list):
        raise ValueError('Port services configuration must be a list')
    seen = set()
    for service in services:
        if service['manager'] not in ('systemd', 'docker', 'pm2'):
            raise ValueError('Unsupported service manager')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.@-]*', service['target']):
            raise ValueError('Invalid service target')
        if service['id'] in seen:
            raise ValueError('Duplicate service id')
        seen.add(service['id'])
        for binding in service['ports']:
            if binding['protocol'] not in ('TCP', 'UDP') or not 1 <= int(binding['port']) <= 65535:
                raise ValueError('Invalid configured port')
    return services


def parse_sockets(output):
    groups = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 6 or parts[0] not in ('tcp', 'udp'):
            continue
        try:
            address, port = parts[4].rsplit(':', 1)
            port = int(port)
        except ValueError:
            continue
        key = (parts[0].upper(), port)
        group = groups.setdefault(key, {'addresses': set(), 'owners': set()})
        group['addresses'].add(address)
        group['owners'].update(f'{name} (PID {pid})' for name, pid in re.findall(r'"([^\"]+)",pid=(\d+)', line))
    return groups


def parse_pm2_processes(output):
    """PM2 may prefix jlist JSON with daemon startup notices or ANSI colors."""
    output = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', output)
    decoder = json.JSONDecoder()
    for match in re.finditer(r'^\s*\[', output, re.MULTILINE):
        start = output.find('[', match.start())
        try:
            processes, end = decoder.raw_decode(output[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(processes, list) and all(isinstance(item, dict) and isinstance(item.get('name'), str) for item in processes):
            return processes
    raise RuntimeError('PM2 jlist did not return a valid process list. Check PM2 under the dashboard operating-system user.')


def service_running(service):
    target = service['target']
    if service['manager'] == 'systemd':
        return command(['systemctl', 'show', target, '--property=ActiveState', '--value']).strip() in ('active', 'activating')
    if service['manager'] == 'docker':
        return command(['docker', 'inspect', '--format', '{{.State.Running}}', target]).strip() == 'true'
    processes = parse_pm2_processes(command(['pm2', 'jlist']))
    match = next((p for p in processes if p['name'] == target), None)
    if match is None:
        raise RuntimeError('PM2 process not found')
    return match.get('pm2_env', {}).get('status') == 'online'


def inventory():
    sockets = parse_sockets(command(['ss', '-H', '-tulpn']))
    errors = []
    try:
        services = configured_services()
    except (ValueError, KeyError, TypeError, OSError) as exc:
        services = []
        errors.append(f'Service configuration unavailable: {exc}')
    states = {}
    if not services:
        errors.append('Start/Stop setup required: create port_services.json in the dashboard project, or set PORT_SERVICES_FILE to your service mapping file. Unmapped ports are read-only.')
    if not os.getenv('PORT_CONTROL_TOKEN'):
        errors.append('Start/Stop disabled: set PORT_CONTROL_TOKEN in the dashboard environment and restart the dashboard. Enter that same token below.')
    for service in services:
        try:
            states[service['id']] = service_running(service)
        except (RuntimeError, ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired) as exc:
            states[service['id']] = None
            errors.append(f"{service.get('name', service['id'])}: {exc}")
    keys = set(sockets)
    for service in services:
        keys.update((p['protocol'], int(p['port'])) for p in service['ports'])
    rows = []
    for protocol, port in sorted(keys, key=lambda key: (key[1], key[0])):
        group = sockets.get((protocol, port), {'addresses': set(), 'owners': set()})
        matches = [s for s in services if any(p['protocol'] == protocol and int(p['port']) == port for p in s['ports'])]
        service = matches[0] if len(matches) == 1 else None
        running = states.get(service['id']) if service else None
        rows.append(dict(id=f'{protocol}-{port}', port=port, protocol=protocol,
                         address=' · '.join(sorted(group['addresses'])) or '—',
                         owner=' · '.join(sorted(group['owners'])) or 'Not reported',
                         service=service.get('name', service['target']) if service else 'Unmanaged',
                         service_id=service['id'] if service else '',
                         status=('Running' if running else 'Stopped') if running is not None else ('Bound' if group['addresses'] else 'Unknown'),
                         bound=bool(group['addresses']), running=running,
                         controllable=service is not None and running is not None and bool(os.getenv('PORT_CONTROL_TOKEN'))))
    return rows, errors


def control(service_id, action, token):
    secret = os.getenv('PORT_CONTROL_TOKEN', '')
    if not secret or not hmac.compare_digest(secret, token or ''):
        raise PermissionError('Invalid service control token')
    if action not in ('start', 'stop'):
        raise ValueError('Invalid action')
    with _LOCK:
        service = next((s for s in configured_services() if s['id'] == service_id), None)
        if service is None:
            raise ValueError('Service is not configured')
        # Never allow the dashboard to stop its own process manager entry.
        if service['target'] in ('homelab-dashboard', 'homelab-dashboard.service'):
            raise ValueError('Dashboard self-control is disabled')
        if action == 'start':
            sockets = parse_sockets(command(['ss', '-H', '-tulpn']))
            if not service_running(service) and any((p['protocol'], int(p['port'])) in sockets for p in service['ports']):
                raise RuntimeError('A configured port is already occupied; start cancelled')
        command([{'systemd': 'systemctl', 'docker': 'docker', 'pm2': 'pm2'}[service['manager']], action, service['target']])
        actual = service_running(service)
        if actual != (action == 'start'):
            raise RuntimeError('Service manager has not confirmed the requested state; refresh status')
