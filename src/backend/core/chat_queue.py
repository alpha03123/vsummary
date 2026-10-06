"""Bounded, actor-fair chat admission shared across API processes."""
from contextlib import contextmanager
from datetime import timedelta
from threading import Event, Thread
import json
import logging
import time

from sqlalchemy import text
from backend.core.context import WorkspaceContext
from backend.core.quota import UsageRecord


class ChatQueueFull(RuntimeError):
    pass


class ChatRequestCancelled(RuntimeError):
    pass


class SqlChatQueue:
    def __init__(self, sessions, *, capacity=3, waiting_limit=30, per_actor_waiting=2,
                 waiting_seconds=60, lease_seconds=120, heartbeat_seconds=20, poll_seconds=0.25):
        if min(capacity, waiting_limit, per_actor_waiting, waiting_seconds, heartbeat_seconds) <= 0 or lease_seconds <= heartbeat_seconds or poll_seconds <= 0:
            raise ValueError("Invalid chat queue limits.")
        self.sessions = sessions
        self.capacity, self.waiting_limit, self.per_actor_waiting = capacity, waiting_limit, per_actor_waiting
        self.waiting_seconds, self.lease_seconds = waiting_seconds, lease_seconds
        self.heartbeat_seconds, self.poll_seconds = heartbeat_seconds, poll_seconds

    @staticmethod
    def _lock(session):
        session.execute(text("INSERT INTO chat_queue_state (id) VALUES ('chat') ON DUPLICATE KEY UPDATE id=id"))
        session.execute(text("SELECT id FROM chat_queue_state WHERE id='chat' FOR UPDATE"))
        now = session.scalar(text("SELECT UTC_TIMESTAMP()"))
        session.execute(text("UPDATE chat_requests SET status='failed',finished_at=:now WHERE status IN ('queued','running','cancelling') AND lease_expires_at<:now"), {"now": now})
        return now

    def enqueue(self, context, operation_id):
        with self.sessions.begin() as session:
            now = self._lock(session)
            waiting = session.scalar(text("SELECT COUNT(*) FROM chat_requests WHERE status='queued'"))
            own = session.scalar(text("SELECT COUNT(*) FROM chat_requests WHERE status='queued' AND actor_id=:actor"), {"actor": context.actor_id})
            if waiting >= self.waiting_limit or own >= self.per_actor_waiting:
                raise ChatQueueFull("对话请求较多，请稍后重试。")
            session.execute(text("""INSERT INTO chat_requests
                (id,workspace_id,actor_id,status,created_at,lease_expires_at)
                VALUES (:id,:workspace,:actor,'queued',:now,:expires)"""),
                {"id": operation_id, "workspace": context.workspace_id, "actor": context.actor_id,
                 "now": now, "expires": now + timedelta(seconds=self.waiting_seconds)})

    def get(self, context, operation_id):
        with self.sessions() as session:
            row = session.execute(text("SELECT id,status,created_at,started_at,finished_at FROM chat_requests WHERE id=:id AND workspace_id=:workspace AND actor_id=:actor"),
                {"id": operation_id, "workspace": context.workspace_id, "actor": context.actor_id}).mappings().first()
            return dict(row) if row is not None else None

    def list_requests(self, *, actor_id=None, status=None, offset=0, limit=50):
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError('Invalid chat pagination.')
        if status is not None and status not in {'queued', 'running', 'cancelling', 'succeeded', 'failed', 'cancelled'}:
            raise ValueError('Invalid chat status.')
        filters, parameters = [], {'offset': offset, 'limit': limit}
        if actor_id is not None:
            filters.append('actor_id=:actor')
            parameters['actor'] = actor_id
        if status is not None:
            filters.append('status=:status')
            parameters['status'] = status
        where = ' WHERE ' + ' AND '.join(filters) if filters else ''
        with self.sessions() as session:
            total = session.scalar(text('SELECT COUNT(*) FROM chat_requests' + where), parameters)
            rows = session.execute(text('SELECT id,workspace_id,actor_id,status,model_profile,accounting_status,created_at,started_at,finished_at FROM chat_requests' + where
                                        + ' ORDER BY sequence DESC LIMIT :limit OFFSET :offset'), parameters).mappings().all()
            return {'total': total, 'items': [dict(row) for row in rows]}

    def try_start(self, context, operation_id):
        with self.sessions.begin() as session:
            now = self._lock(session)
            own = session.execute(text("SELECT status FROM chat_requests WHERE id=:id AND actor_id=:actor AND workspace_id=:workspace"),
                {"id": operation_id, "actor": context.actor_id, "workspace": context.workspace_id}).first()
            if own is None or own.status not in ('queued', 'running'):
                raise ChatRequestCancelled("对话等待已结束，请重新发起。")
            if own.status == 'running':
                return True
            count = session.scalar(text("SELECT COUNT(*) FROM chat_requests WHERE status IN ('running','cancelling')"))
            if count >= self.capacity:
                return False
            selected = session.scalar(text("""SELECT queued.id FROM chat_requests AS queued
                WHERE queued.status='queued' AND NOT EXISTS (
                    SELECT 1 FROM chat_requests AS active WHERE active.actor_id=queued.actor_id AND active.status IN ('running','cancelling'))
                ORDER BY queued.sequence LIMIT 1"""))
            if selected != operation_id:
                return False
            session.execute(text("UPDATE chat_requests SET status='running',started_at=:now,lease_expires_at=:expires WHERE id=:id"),
                {"id": operation_id, "now": now, "expires": now + timedelta(seconds=self.lease_seconds)})
            return True

    def attach_reservation(self, operation_id, reservation_id, model_profile):
        with self.sessions.begin() as session:
            session.execute(text("UPDATE chat_requests SET reservation_id=:reservation,model_profile=:profile,accounting_status='pending' WHERE id=:id"),
                            {"id": operation_id, "reservation": reservation_id, "profile": model_profile})

    def cancel(self, context, operation_id):
        with self.sessions.begin() as session:
            session.execute(text("""UPDATE chat_requests SET status=CASE WHEN status='queued' THEN 'cancelled' ELSE 'cancelling' END
                WHERE id=:id AND actor_id=:actor AND workspace_id=:workspace AND status IN ('queued','running')"""),
                {"id": operation_id, "actor": context.actor_id, "workspace": context.workspace_id})

    def finish(self, operation_id, status):
        if status not in {'succeeded', 'failed', 'cancelled'}:
            raise ValueError("Invalid terminal chat status.")
        with self.sessions.begin() as session:
            session.execute(text("UPDATE chat_requests SET status=:status,finished_at=UTC_TIMESTAMP() WHERE id=:id AND status IN ('queued','running','cancelling')"), {"id": operation_id, "status": status})

    def account(self, operation_id, guard, usage_store):
        with self.sessions.begin() as session:
            row = session.execute(text("SELECT * FROM chat_requests WHERE id=:id FOR UPDATE"), {"id": operation_id}).mappings().first()
            if row is None or row['accounting_status'] != 'pending' or row['status'] not in {'succeeded','failed','cancelled'}:
                return
            context = WorkspaceContext(row['workspace_id'], row['actor_id'], row['id'])
            totals = usage_store.summarize(range_key='all', workspace_id=context.workspace_id, actor_id=context.actor_id, operation_ids=[operation_id]).total
            usage = UsageRecord(units=1, operation='agent_chat', operation_id=operation_id,
                                model_profile=row['model_profile'], input_tokens=totals.prompt_tokens, output_tokens=totals.completion_tokens)
            if row['status'] == 'succeeded':
                guard.settle(row['reservation_id'], usage)
            else:
                guard.release(row['reservation_id'], 'chat ' + row['status'])
            session.execute(text("UPDATE chat_requests SET accounting_status='settled',`usage`=:usage WHERE id=:id"),
                            {"id": operation_id, "usage": json.dumps({'input_tokens': usage.input_tokens, 'output_tokens': usage.output_tokens})})

    def reconcile(self, guard, usage_store):
        with self.sessions.begin() as session:
            self._lock(session)
            pending = session.scalars(text("SELECT id FROM chat_requests WHERE accounting_status='pending' AND status IN ('succeeded','failed','cancelled') LIMIT 20")).all()
        for operation_id in pending:
            try:
                self.account(operation_id, guard, usage_store)
            except Exception:
                logging.getLogger(__name__).exception("Chat accounting remains pending", extra={'operation_id': operation_id})

    @contextmanager
    def running(self, context, operation_id):
        stop, lost = Event(), Event()
        def heartbeat():
            while not stop.wait(self.heartbeat_seconds):
                try:
                    with self.sessions.begin() as session:
                        changed = session.execute(text("UPDATE chat_requests SET lease_expires_at=DATE_ADD(UTC_TIMESTAMP(), INTERVAL :seconds SECOND) WHERE id=:id AND status='running'"),
                                                  {'id': operation_id, 'seconds': self.lease_seconds}).rowcount
                    if not changed:
                        lost.set()
                        return
                except Exception:
                    lost.set()
                    logging.getLogger(__name__).exception("Chat lease renewal failed")
                    return
        worker = Thread(target=heartbeat, daemon=True, name='chat-lease')
        worker.start()
        last_check=0.0
        def check(force=False):
            nonlocal last_check
            if lost.is_set():
                raise ChatRequestCancelled("对话已取消或连接失效。")
            now=time.monotonic()
            if not force and now-last_check<self.poll_seconds:
                return
            last_check=now
            state = self.get(context, operation_id)
            if state is None or state['status'] != 'running':
                raise ChatRequestCancelled("对话已取消。")
        try:
            yield check
        finally:
            stop.set()
            worker.join(timeout=self.heartbeat_seconds)
