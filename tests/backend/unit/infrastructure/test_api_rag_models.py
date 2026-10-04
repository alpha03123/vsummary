import httpx
import pytest

from backend.video_summary.infrastructure.rag.agent_memory.api_models import ApiEmbedding, ApiReranker, ModelApiError, ModelApiSettings


def test_embedding_restores_input_order_and_checks_dimensions():
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"data": [
        {"index": 1, "embedding": [3, 4]}, {"index": 0, "embedding": [1, 2]}]}))) as client:
        model = ApiEmbedding(ModelApiSettings("https://model.example/v1/embeddings", "embed", "key", dimensions=2),
            batch_size=2, client=client)
        assert model.get_text_embedding_batch(["a", "b"]) == [[1.0, 2.0], [3.0, 4.0]]


@pytest.mark.parametrize("data", [
    [{"index": 0, "embedding": [1]}],
    [{"index": 0, "embedding": [1, 2]}, {"index": 0, "embedding": [3, 4]}],
    [{"index": 0, "embedding": [1, 2]}],
])
def test_invalid_embedding_fails_without_publishing_partial_vectors(data):
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"data": data}))) as client:
        model = ApiEmbedding(ModelApiSettings("https://model.example/embeddings", "embed", "key", dimensions=2), batch_size=2, client=client)
        with pytest.raises(ModelApiError) as error:
            model.get_text_embedding_batch(["a", "b"])
        assert not error.value.retryable


def test_reranking_preserves_document_association():
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"results": [
        {"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.1}]}))) as client:
        model = ApiReranker(ModelApiSettings("https://model.example/rerank", "rank", "key"), client=client)
        assert model.score(query="q", texts=["a", "b"]) == [0.1, 0.9]


def test_rate_limit_is_a_retryable_job_error():
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(429, headers={"Retry-After": "12"}))) as client:
        model = ApiEmbedding(ModelApiSettings("https://model.example/embeddings", "embed", "key", dimensions=2), batch_size=2, client=client)
        with pytest.raises(ModelApiError) as error:
            model.get_text_embedding("a")
        assert error.value.retryable and error.value.retry_after == 12
