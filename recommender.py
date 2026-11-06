"""Deterministic, explainable Circle recommendations backed by SQLite."""
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SNAPSHOT_DATE = '2026-09-21'


def connect(path=':memory:'):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    return db


def seed(db, data_dir=ROOT / 'data'):
    """Load a fresh database transactionally; retain every supplied profile field."""
    db.executescript((ROOT / 'schema.sql').read_text())
    with db:
        for table in ('activity', 'memberships', 'circle_tags', 'user_interests', 'circles', 'users', 'topics'):
            db.execute(f'DELETE FROM {table}')
        for table in ('topics', 'users', 'circles', 'memberships', 'activity'):
            records = json.loads((Path(data_dir) / f'{table}.json').read_text())
            for record in records:
                record = dict(record)
                interests = record.pop('topic_interests', [])
                tags = record.pop('tags', [])
                columns = ','.join(record)
                db.execute(f'INSERT INTO {table} ({columns}) VALUES ({",".join("?" for _ in record)})', tuple(record.values()))
                if table == 'users':
                    db.executemany('INSERT INTO user_interests VALUES (?,?)', [(record['id'], t) for t in set(interests)])
                if table == 'circles':
                    db.executemany('INSERT INTO circle_tags VALUES (?,?)', [(record['id'], t) for t in set(tags)])


def instant(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).replace(tzinfo=timezone.utc)


def recommend(db, user_id, limit=5, as_of=SNAPSHOT_DATE):
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 20:
        raise ValueError('limit must be an integer from 1 to 20')
    now = instant(as_of)
    if not db.execute('SELECT 1 FROM users WHERE id=?', (user_id,)).fetchone():
        raise LookupError('User not found')
    interests = {r[0] for r in db.execute('SELECT topic_slug FROM user_interests WHERE user_id=?', (user_id,))}
    inferred = {r[0] for r in db.execute('SELECT c.topic FROM circles c JOIN memberships m ON c.id=m.circle_id WHERE m.user_id=? AND c.topic IS NOT NULL', (user_id,))}
    labels = dict(db.execute('SELECT slug,label FROM topics'))
    tags = {}
    for row in db.execute('SELECT circle_id,tag FROM circle_tags'):
        tags.setdefault(row[0], set()).add(row[1])
    candidates = []
    rows = db.execute('''SELECT c.* FROM circles c WHERE access='public'
        AND (max_members IS NULL OR member_count<max_members)
        AND NOT EXISTS (SELECT 1 FROM memberships m WHERE m.circle_id=c.id AND m.user_id=?)''', (user_id,))
    for row in rows:
        c = dict(row)
        age = (now - instant(c['last_activity_at'])).total_seconds() / 86400
        # Future-dated activity cannot be treated as observed evidence.
        if age < 0 or age > 90:
            continue
        signals = tags.get(c['id'], set()) | ({c['topic']} if c['topic'] else set())
        direct = interests & signals
        primary = c['topic'] in interests
        affinity = (0.65 if primary else 0) + 0.25 * len(direct) / max(1, len(interests))
        if not interests:
            affinity = 0.35 if c['topic'] in inferred else 0
        recency = math.exp(-age / 30)
        # Log saturation prevents large, noisy groups from dominating.
        volume = (min(1, math.log1p(c['feed_posts_30d']) / math.log1p(20)) +
                  min(1, math.log1p(c['chat_messages_30d']) / math.log1p(100))) / 2
        health = 0.6 * recency + 0.4 * volume
        score = 0.75 * affinity + 0.25 * health
        reasons = []
        if direct:
            ordered = sorted(direct, key=lambda t: (t != c['topic'], t))
            reasons.append('Matches your interest in ' + ', '.join(labels.get(t, t) for t in ordered[:2]) + '.')
        elif not interests and c['topic'] in inferred:
            reasons.append('Explores a topic from Circles you already belong to.')
        else:
            reasons.append('An active community to explore and build supportive connections.')
        if age <= 30:
            reasons.append('Members have been active within the past month.')
        else:
            reasons.append('Members have been active within the past three months.')
        reasons.append('Open to join.' if c['join_policy'] == 'open' else 'You can request to join.')
        candidates.append({**c, 'score': round(score, 6), 'explanation': ' '.join(reasons)})
    candidates.sort(key=lambda c: (-c['score'], c['id']))
    # At most one Circle per primary topic, even when fewer than limit survive.
    selected, seen = [], set()
    for c in candidates:
        key = c['topic'] or 'untagged:' + c['slug']
        if key in seen:
            continue
        seen.add(key)
        selected.append({k: c[k] for k in ('id', 'name', 'slug', 'topic', 'format', 'join_policy', 'score', 'explanation')})
        if len(selected) == limit:
            break
    return {'user_id': user_id, 'as_of': as_of, 'recommendations': selected}
