"""RQ reserves `job_id=` on Queue.enqueue for the Redis job id.

Passing our application job_id only as a keyword silently drops it from the
callable kwargs and raises TypeError at worker runtime. These tests lock the
positional+keyword pattern used by enqueue_import_job / enqueue_enrichment_job.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from scrapegraph_worker.jobs import enqueue_enrichment_job, enqueue_import_job


def test_enqueue_import_job_passes_job_id_positionally() -> None:
    mock_queue = MagicMock()
    with (
        patch("scrapegraph_worker.jobs.JobStore") as mock_store_cls,
        patch("scrapegraph_worker.jobs.get_queue", return_value=mock_queue),
        patch("scrapegraph_worker.jobs.load_settings") as mock_settings,
    ):
        settings = MagicMock()
        settings.job_store_url = "sqlite:///./test.db"
        settings.queue.job_timeout_seconds = 60
        mock_settings.return_value = settings
        mock_store_cls.return_value = MagicMock()

        job_id = enqueue_import_job(repo_path="/scrapegraph", target=5)

    args, kwargs = mock_queue.enqueue.call_args
    assert args[1] == job_id
    assert kwargs.get("job_id") == job_id
    assert kwargs["repo_path"] == "/scrapegraph"
    assert kwargs["target"] == 5


def test_enqueue_enrichment_job_passes_job_id_positionally() -> None:
    mock_queue = MagicMock()
    with (
        patch("scrapegraph_worker.jobs.JobStore") as mock_store_cls,
        patch("scrapegraph_worker.jobs.get_queue", return_value=mock_queue),
        patch("scrapegraph_worker.jobs.load_settings") as mock_settings,
    ):
        settings = MagicMock()
        settings.job_store_url = "sqlite:///./test.db"
        settings.queue.job_timeout_seconds = 60
        mock_settings.return_value = settings
        mock_store_cls.return_value = MagicMock()

        job_id = enqueue_enrichment_job(company_ids=["c1", "c2"])

    args, kwargs = mock_queue.enqueue.call_args
    assert args[1] == job_id
    assert kwargs.get("job_id") == job_id
    assert kwargs["company_ids"] == ["c1", "c2"]
