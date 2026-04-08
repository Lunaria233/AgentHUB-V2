from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SETaskEvalCase:
    case_id: str
    title: str
    mode: str
    task_type: str
    description: str
    user_task: str
    verify_command: str
    fixture_name: str
    constraints: dict[str, object] = field(default_factory=dict)

    def fixture_path(self, fixtures_root: Path) -> Path:
        return fixtures_root / self.fixture_name


def load_eval_cases() -> list[SETaskEvalCase]:
    return [
        SETaskEvalCase(
            case_id="req_csv_mean",
            title="Implement CSV mean utility",
            mode="requirement_to_code",
            task_type="requirement_to_code",
            description="Implement a CSV mean function from requirement and pass tests.",
            user_task=(
                "实现 `stats_utils.mean_from_csv(path)`：读取 CSV 文件第一列数字并返回平均值；"
                "需要忽略空行与非数字值；不能修改测试文件。"
            ),
            verify_command='python -m unittest discover -s tests -p "test_*.py"',
            fixture_name="req_csv_mean",
            constraints={"allow_modify_tests": False, "allow_install_dependency": False, "allow_network": False, "max_iterations": 4},
        ),
        SETaskEvalCase(
            case_id="req_user_register",
            title="Add registration logic with validation",
            mode="requirement_to_code",
            task_type="requirement_to_code",
            description="Generate registration logic with parameter validation and duplicate checks.",
            user_task=(
                "为 `user_service.py` 增加 `register_user` 逻辑：校验 email 格式和密码长度，"
                "用户名不能重复，返回结构化结果。不要修改测试文件。"
            ),
            verify_command='python -m unittest discover -s tests -p "test_*.py"',
            fixture_name="req_user_register",
            constraints={"allow_modify_tests": False, "allow_install_dependency": False, "allow_network": False, "max_iterations": 4},
        ),
        SETaskEvalCase(
            case_id="req_cache_wrapper",
            title="Add in-memory cache behavior",
            mode="requirement_to_code",
            task_type="requirement_to_code",
            description="Add cache wrapper for repeated calls while keeping output unchanged.",
            user_task=(
                "给 `weather_service.py` 增加简单内存缓存：同一个城市重复查询时避免重复调用远端函数，"
                "并保证返回结构与现有测试一致。"
            ),
            verify_command='python -m unittest discover -s tests -p "test_*.py"',
            fixture_name="req_cache_wrapper",
            constraints={"allow_modify_tests": False, "allow_install_dependency": False, "allow_network": False, "max_iterations": 4},
        ),
        SETaskEvalCase(
            case_id="fix_pricing_bug",
            title="Fix failing pricing tests",
            mode="feedback_to_fix",
            task_type="feedback_to_fix",
            description="Fix discount calculation bug without changing tests.",
            user_task="修复当前 failing test，不允许修改测试文件；重点检查折扣计算边界。",
            verify_command='python -m unittest discover -s tests -p "test_*.py"',
            fixture_name="fix_pricing_bug",
            constraints={"allow_modify_tests": False, "allow_install_dependency": False, "allow_network": False, "max_iterations": 4},
        ),
        SETaskEvalCase(
            case_id="fix_import_error",
            title="Fix import error",
            mode="feedback_to_fix",
            task_type="feedback_to_fix",
            description="Repair import chain and make adapter tests pass.",
            user_task="修复 import 报错并让测试通过；不允许修改测试文件。",
            verify_command='python -m unittest discover -s tests -p "test_*.py"',
            fixture_name="fix_import_error",
            constraints={"allow_modify_tests": False, "allow_install_dependency": False, "allow_network": False, "max_iterations": 4},
        ),
        SETaskEvalCase(
            case_id="fix_parser_validation",
            title="Fix parser validation bug",
            mode="feedback_to_fix",
            task_type="feedback_to_fix",
            description="Fix argument validation path and preserve normal behavior.",
            user_task="修复解析器参数校验 bug，让异常和正常路径都符合测试预期。",
            verify_command='python -m unittest discover -s tests -p "test_*.py"',
            fixture_name="fix_parser_validation",
            constraints={"allow_modify_tests": False, "allow_install_dependency": False, "allow_network": False, "max_iterations": 4},
        ),
    ]
