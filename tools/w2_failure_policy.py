"""Case isolation rules; poor measured performance never triggers a retry."""
TERMINAL = frozenset(('measured', 'blocked_scope', 'skipped_failed'))

def decide(status, environment_healthy, attempt, max_attempts=2):
    if not environment_healthy:
        return 'halt'
    if status in TERMINAL:
        return 'continue'
    return 'retry' if attempt < max_attempts else 'skip'

def summarize_record(record, decision):
    result = dict(record)
    if decision == 'skip':
        result.update(status='skipped_failed', original_status=record['status'],
                      skip_reason='Case attempts exhausted; shared environment verified clean. Original attempt outcomes retained.')
    elif decision == 'halt':
        result.update(status='environment_blocked', original_status=record['status'],
                      stop_reason='Shared environment could not be verified after bounded recovery.')
    return result
