import lancedb
from llama_index.core.embeddings import MockEmbedding

from backend.video_summary.infrastructure.rag.agent_memory.retrieval import INDEX_TABLE_NAME, SeriesRetrievalService


class EmptyWorkspace:
    def list_series(self):
        return []


def test_refresh_of_a_workspace_without_documents_succeeds_and_leaves_no_table(tmp_path):
    service = SeriesRetrievalService(workspace=EmptyWorkspace(), db_uri=str(tmp_path), embed_model=MockEmbedding(embed_dim=8))
    service.refresh_all()
    service.refresh_all()
    assert INDEX_TABLE_NAME not in lancedb.connect(str(tmp_path)).table_names()
