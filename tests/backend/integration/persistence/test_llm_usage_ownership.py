"""Check actual SQL ownership filters across every usage aggregation."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import bindparam, text

from backend.core.context import WorkspaceContext
from backend.core.ids import new_ulid
from backend.core.request_context import bind_workspace_context
from backend.shared.llm.usage import LlmUsageRecord, MySqlLlmUsageStore


def record(tokens, category="generation", model="owned", created_at=None):
    return LlmUsageRecord(created_at or datetime.now(timezone.utc), category, "openai", "https://example.invalid/v1", model, tokens // 2, tokens - tokens // 2, tokens)


@pytest.fixture
def ledger(mysql_sessions):
    workspace, other_workspace = new_ulid(), new_ulid()
    actor, other_actor = new_ulid(), new_ulid()
    contexts = [
        WorkspaceContext(workspace, actor, new_ulid()),
        WorkspaceContext(workspace, other_actor, new_ulid()),
        WorkspaceContext(other_workspace, actor, new_ulid()),
    ]
    store = MySqlLlmUsageStore(mysql_sessions)
    legacy_id = new_ulid()
    try:
        yield store, contexts, legacy_id
    finally:
        with mysql_sessions.begin() as session:
            session.execute(text("DELETE FROM llm_usage WHERE actor_id IN :actors OR id = :legacy").bindparams(bindparam("actors", expanding=True)), {"actors": [actor, other_actor], "legacy": legacy_id})


def test_all_aggregates_use_workspace_and_actor_filters(mysql_sessions, ledger):
    store, (owner, member, elsewhere), legacy_id = ledger
    for context, usage in [(owner, record(30)), (owner, record(40, "chat")), (member, record(200, model="other-member")), (elsewhere, record(300, model="other-workspace"))]:
        with bind_workspace_context(context):
            store.record(usage)
    with mysql_sessions.begin() as session:
        session.execute(text("""INSERT INTO llm_usage
            (id,created_at,category,provider,base_url,model,prompt_tokens,completion_tokens,total_tokens)
            VALUES (:id,:created,'generation','openai','','unattributed',250,250,500)"""), {"id": legacy_id, "created": datetime.now(timezone.utc)})

    own = store.summarize(range_key="all", workspace_id=owner.workspace_id, actor_id=owner.actor_id)
    assert own.total.total_tokens == 70
    assert own.total.prompt_tokens + own.total.completion_tokens == 70
    assert {item.category: item.total_tokens for item in own.by_category} == {"generation": 30, "chat": 40}
    assert [(item.model, item.total_tokens) for item in own.by_provider] == [("owned", 70)]
    assert len(own.recent) == 2 and all(item.model == "owned" for item in own.recent)
    assert sum(item.total_tokens for item in own.timeline) == 70
    assert store.summarize(range_key="all", actor_id=owner.actor_id).total.total_tokens == 370
    assert store.summarize(range_key="all", workspace_id=owner.workspace_id).total.total_tokens == 270
    with mysql_sessions() as session:
        assert session.execute(text("SELECT workspace_id,actor_id FROM llm_usage WHERE model='owned' AND actor_id=:actor"), {"actor": owner.actor_id}).all() == [(owner.workspace_id, owner.actor_id)] * 2


def test_range_and_empty_tenant_results(ledger):
    store, (owner, member, _), _ = ledger
    now = datetime.now(timezone.utc)
    with bind_workspace_context(owner):
        store.record(record(20, created_at=now - timedelta(days=31)))
        store.record(record(10, created_at=now))
    assert store.summarize(range_key="7d", workspace_id=owner.workspace_id, actor_id=owner.actor_id, now=now).total.total_tokens == 10
    empty = store.summarize(range_key="all", workspace_id=member.workspace_id, actor_id=member.actor_id)
    assert empty.total.total_tokens == 0
    assert empty.by_category == empty.by_provider == empty.recent == empty.timeline == []
    with pytest.raises(ValueError, match="actor_id"):
        store.summarize(range_key="all", actor_id="")
    with pytest.raises(ValueError, match="workspace_id"):
        store.summarize(range_key="all", workspace_id=" ")


def test_async_thread_contexts_do_not_cross_attribute_usage(ledger):
    store, (owner, member, _), _ = ledger
    async def write(context, tokens):
        with bind_workspace_context(context):
            await asyncio.to_thread(store.record, record(tokens))
    async def concurrent():
        await asyncio.gather(write(owner, 17), write(member, 19))
    asyncio.run(concurrent())
    assert store.summarize(range_key="all", workspace_id=owner.workspace_id, actor_id=owner.actor_id).total.total_tokens == 17
    assert store.summarize(range_key="all", workspace_id=member.workspace_id, actor_id=member.actor_id).total.total_tokens == 19


def test_new_usage_without_context_is_rejected(ledger):
    store, _, _ = ledger
    with pytest.raises(RuntimeError, match="workspace context"):
        store.record(record(10))
