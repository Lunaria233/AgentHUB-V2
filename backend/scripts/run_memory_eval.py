from __future__ import annotations

import json
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = CURRENT_DIR.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.apps.chat.manifest import CHAT_APP_MANIFEST
from app.platform.memory.evaluation import MemoryEvaluator, isolated_memory_service
from app.platform.runtime.orchestrator import get_orchestrator


def main() -> None:
    orchestrator = get_orchestrator()
    with isolated_memory_service(orchestrator.memory_service) as eval_service:
        evaluator = MemoryEvaluator(eval_service)
        summary = evaluator.run_default_suite(app_id="chat", profile=CHAT_APP_MANIFEST.profiles.memory_profile)
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
