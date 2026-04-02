from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.platform.rag.evaluation import RAGEvaluator
from app.platform.runtime.orchestrator import get_orchestrator


def main() -> None:
    orchestrator = get_orchestrator()
    summary = RAGEvaluator(
        settings=orchestrator.settings,
        embedder=orchestrator.rag_embedder,
        model_client=orchestrator.model_client,
        trace_service=orchestrator.trace_service,
    ).run(app_id="chat")
    print(
        json.dumps(
            {
                "average_recall_at_k": summary.average_recall_at_k,
                "average_precision_at_k": summary.average_precision_at_k,
                "average_mrr": summary.average_mrr,
                "average_leakage_rate": summary.average_leakage_rate,
                "average_source_coverage": summary.average_source_coverage,
                "cases": [case.case_id for case in summary.cases],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
