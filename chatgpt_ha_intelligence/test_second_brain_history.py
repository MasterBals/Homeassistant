from __future__ import annotations

import os
import tempfile

with tempfile.TemporaryDirectory(prefix='second-brain-test-') as tmp:
    os.environ['CHATGPT_HA_DATA_DIR'] = tmp

    from state_store import brain_get, brain_status, brain_upsert

    created = brain_upsert(
        topic='test',
        key='stable-key',
        title='Initial finding',
        content='First verified understanding',
        confidence='verified',
        change_reason='Initial verification',
    )
    assert created['action'] == 'created'
    assert created['revision'] == 1

    updated = brain_upsert(
        topic='test',
        key='stable-key',
        title='Corrected finding',
        content='Second verified understanding',
        confidence='verified',
        change_reason='Later analysis disproved the original interpretation',
    )
    assert updated['action'] == 'updated'
    assert updated['revision'] == 2

    entry = brain_get('test', 'stable-key', include_history=True)
    assert entry is not None
    assert entry['revision'] == 2
    assert len(entry['history']) == 1
    old = entry['history'][0]
    assert old['revision'] == 1
    assert old['content'] == 'First verified understanding'
    assert old['created_at']
    assert old['updated_at']
    assert old['archived_at']
    assert old['superseded_reason'] == 'Later analysis disproved the original interpretation'

    unchanged = brain_upsert(
        topic='test',
        key='stable-key',
        title='Corrected finding',
        content='Second verified understanding',
        confidence='verified',
        change_reason='No semantic change',
    )
    assert unchanged['action'] == 'unchanged'
    assert unchanged['revision'] == 2
    assert brain_status()['revisions'] == 1

print('Second Brain revision-history regression test: OK')
