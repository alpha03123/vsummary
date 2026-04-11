# LangGraph Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new backend agent skeleton based on LangGraph + DSPy for series query handling, without extending the legacy custom runtime.

**Architecture:** Keep the existing API entrypoints, but introduce a parallel `agent_graph` stack for series questions. The graph owns orchestration, DSPy owns classification/splitting/answer modules, and retrieval stays behind a dedicated adapter that initially wraps the current workspace evidence reads.

**Tech Stack:** Python, LangGraph, DSPy, existing FastAPI backend, existing workspace storage.

---

### Task 1: Add foundational dependencies and graph package skeleton

**Files:**
- Modify: `E:\gittools\self\video_include\.worktrees\codex-langgraph-refactor\requirements.txt`
- Create: `E:\gittools\self\video_include\.worktrees\codex-langgraph-refactor\src\backend\agent_graph\__init__.py`
- Create: `E:\gittools\self\video_include\.worktrees\codex-langgraph-refactor\src\backend\agent_graph\state.py`
- Create: `E:\gittools\self\video_include\.worktrees\codex-langgraph-refactor\src\backend\agent_graph\graph.py`
- Test: `E:\gittools\self\video_include\.worktrees\codex-langgraph-refactor\tests\test_agent_graph_scaffold.py`

- [ ] **Step 1: Write the failing test**

```python
def test_build_series_graph_returns_compiled_graph():
    graph = build_series_agent_graph(...)
    assert graph is not None
    assert hasattr(graph, "invoke")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest -v tests.test_agent_graph_scaffold`
Expected: FAIL with import/module/function missing errors

- [ ] **Step 3: Write minimal implementation**

Create a minimal `AgentGraphState` typed dict / model and a `build_series_agent_graph(...)` function that returns a compiled LangGraph with placeholder nodes.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest -v tests.test_agent_graph_scaffold`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add requirements.txt src/backend/agent_graph tests/test_agent_graph_scaffold.py
git commit -m "feat: add langgraph agent scaffold"
```

### Task 2: Add DSPy programs for classify, compare split, and answer synthesis

**Files:**
- Create: `E:\gittools\self\video_include\.worktrees\codex-langgraph-refactor\src\backend\agent_graph\programs.py`
- Create: `E:\gittools\self\video_include\.worktrees\codex-langgraph-refactor\src\backend\agent_graph\models.py`
- Test: `E:\gittools\self\video_include\.worktrees\codex-langgraph-refactor\tests\test_agent_graph_programs.py`

- [ ] **Step 1: Write the failing test**

```python
def test_series_query_classifier_program_returns_structured_fields():
    result = SeriesQueryClassifierProgram(predictor=stub).run(...)
    assert result.goal == "locate"
    assert result.target_source == "transcript"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest -v tests.test_agent_graph_programs`
Expected: FAIL with import/module/function missing errors

- [ ] **Step 3: Write minimal implementation**

Implement DSPy-backed wrappers with injectable predictors so tests can run without network:
- `SeriesQueryClassifierProgram`
- `CompareSplitProgram`
- `AnswerSynthesisProgram`

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest -v tests.test_agent_graph_programs`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/backend/agent_graph tests/test_agent_graph_programs.py
git commit -m "feat: add dspy agent programs"
```

### Task 3: Add retrieval adapter around current series evidence reads

**Files:**
- Create: `E:\gittools\self\video_include\.worktrees\codex-langgraph-refactor\src\backend\agent_graph\retrieval.py`
- Modify: `E:\gittools\self\video_include\.worktrees\codex-langgraph-refactor\src\backend\video_summary\library\ports.py`
- Test: `E:\gittools\self\video_include\.worktrees\codex-langgraph-refactor\tests\test_agent_graph_retrieval.py`

- [ ] **Step 1: Write the failing test**

```python
def test_series_retrieval_service_dispatches_to_workspace_search():
    service = SeriesRetrievalService(workspace=fake_workspace)
    result = service.search(...)
    assert result["hits"][0]["video_id"] == "video-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest -v tests.test_agent_graph_retrieval`
Expected: FAIL with import/module/function missing errors

- [ ] **Step 3: Write minimal implementation**

Implement a retrieval adapter that wraps:
- summary retrieval
- transcript retrieval
- all retrieval

without moving chunking/indexing logic yet.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest -v tests.test_agent_graph_retrieval`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/backend/agent_graph/retrieval.py src/backend/video_summary/library/ports.py tests/test_agent_graph_retrieval.py
git commit -m "feat: add series retrieval adapter for agent graph"
```

### Task 4: Wire graph nodes for the first series query path

**Files:**
- Modify: `E:\gittools\self\video_include\.worktrees\codex-langgraph-refactor\src\backend\agent_graph\graph.py`
- Create: `E:\gittools\self\video_include\.worktrees\codex-langgraph-refactor\src\backend\agent_graph\nodes.py`
- Test: `E:\gittools\self\video_include\.worktrees\codex-langgraph-refactor\tests\test_agent_graph_series_flow.py`

- [ ] **Step 1: Write the failing test**

```python
def test_series_locate_flow_runs_classify_then_retrieve_then_answer():
    result = run_series_graph(...)
    assert result["answer"]
    assert result["retrieval_results"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest -v tests.test_agent_graph_series_flow`
Expected: FAIL with missing flow wiring

- [ ] **Step 3: Write minimal implementation**

Wire:
- `load_context`
- `classify_query`
- `split_compare`
- `retrieve_evidence`
- `synthesize_answer`

with conditional edges for:
- understand
- locate
- compare

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest -v tests.test_agent_graph_series_flow`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/backend/agent_graph tests/test_agent_graph_series_flow.py
git commit -m "feat: wire first series langgraph flow"
```

### Task 5: Add compatibility service bridge without replacing the old runtime

**Files:**
- Create: `E:\gittools\self\video_include\.worktrees\codex-langgraph-refactor\src\backend\agent_graph\service.py`
- Modify: `E:\gittools\self\video_include\.worktrees\codex-langgraph-refactor\src\backend\api\bootstrap.py`
- Test: `E:\gittools\self\video_include\.worktrees\codex-langgraph-refactor\tests\test_agent_graph_service.py`

- [ ] **Step 1: Write the failing test**

```python
def test_bootstrap_can_build_series_agent_graph_service():
    container = build_api_container(...)
    service = container.get_series_agent_graph_service()
    assert service is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest -v tests.test_agent_graph_service`
Expected: FAIL with attribute/service missing

- [ ] **Step 3: Write minimal implementation**

Add a parallel service constructor in bootstrap. Do not replace the legacy agent service yet.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest -v tests.test_agent_graph_service`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/backend/agent_graph/service.py src/backend/api/bootstrap.py tests/test_agent_graph_service.py
git commit -m "feat: expose langgraph series agent service"
```

### Task 6: Run focused and fast verification

**Files:**
- Modify: `E:\gittools\self\video_include\.worktrees\codex-langgraph-refactor\tests\...` (only if verification reveals breakage)

- [ ] **Step 1: Run focused graph tests**

Run: `python -m unittest -v tests.test_agent_graph_scaffold tests.test_agent_graph_programs tests.test_agent_graph_retrieval tests.test_agent_graph_series_flow tests.test_agent_graph_service`
Expected: PASS

- [ ] **Step 2: Run fast backend regression**

Run: `python scripts/run_backend_tests.py fast`
Expected: PASS, or a clearly documented set of intentional transitional failures

- [ ] **Step 3: If safe, run subjective series cases**

Run: `python scripts/run_agent_subjective_cases.py --manual --continue-on-error --cases series-concept-location series-relationship`
Expected: new graph path can be exercised when wired in

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "test: verify first langgraph series path"
```
