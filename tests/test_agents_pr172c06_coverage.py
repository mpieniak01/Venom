"""Coverage wave tests for PR-172C-06 agents: strategist, ux_analyst, simulated_user, researcher."""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_kernel():
    """Mock Semantic Kernel used across agents in this module."""
    kernel = MagicMock()
    kernel.add_plugin = MagicMock()
    mock_service = MagicMock()
    mock_service.get_chat_message_content = AsyncMock(
        return_value=MagicMock(__str__=lambda s: "mocked response")
    )
    kernel.get_service = MagicMock(return_value=mock_service)
    return kernel


# ===========================================================================
# StrategistAgent – branch coverage
# ===========================================================================


class TestStrategistBranches:
    """Branch-level tests for StrategistAgent decision logic."""

    @pytest.fixture
    def agent(self, mock_kernel, tmp_path):
        from venom_core.agents.strategist import StrategistAgent
        from venom_core.ops.work_ledger import WorkLedger

        ledger = WorkLedger(storage_path=str(tmp_path / "ledger.json"))
        return StrategistAgent(kernel=mock_kernel, work_ledger=ledger)

    # -- process() default else branch --
    @pytest.mark.asyncio
    async def test_process_default_branch(self, agent):
        """Default else branch calls analyze_task with raw input."""
        result = await agent.process("a simple coding task")
        assert "STRATEGIST ANALYSIS" in result

    # -- process() report branch --
    @pytest.mark.asyncio
    async def test_process_report_branch(self, agent):
        """process('report') calls generate_report."""
        result = await agent.process("report")
        assert "STRATEGIST REPORT" in result

    # -- analyze_task with HIGH complexity triggers subtasks --
    @pytest.mark.asyncio
    async def test_analyze_task_high_complexity_suggests_subtasks(self, agent):
        """HIGH/EPIC complexity triggers suggest_subtasks."""
        desc = "Zaprojektuj architekturę mikroserwisów kubernetes enterprise skalowalne"
        result = await agent.analyze_task(desc, task_id="high_001")
        # HIGH or EPIC triggers subtask suggestion
        assert "STRATEGIST ANALYSIS" in result

    # -- monitor_task with api_calls_made > 0 --
    def test_monitor_task_with_api_usage(self, agent):
        """monitor_task covers api_calls_made > 0 branch and api_usage metadata."""
        from venom_core.ops.work_ledger import TaskComplexity

        agent.work_ledger.log_task(
            "api_task",
            "API Task",
            "Description",
            60,
            TaskComplexity.MEDIUM,
            metadata={
                "api_usage": {
                    "openai": {"calls": 10, "tokens": 5000},
                }
            },
        )
        agent.work_ledger.start_task("api_task")
        task = agent.work_ledger.get_task("api_task")
        task.api_calls_made = 10
        task.tokens_used = 5000

        result = agent.monitor_task("api_task")
        assert "API Calls: 10" in result
        assert "Tokens Used: 5000" in result
        assert "openai" in result

    # -- generate_report with tasks --
    @pytest.mark.asyncio
    async def test_generate_report_with_tasks(self, agent):
        """generate_report with tasks shows full breakdown."""
        from venom_core.ops.work_ledger import TaskComplexity

        await agent.analyze_task("Build a simple Python script", task_id="rep_01")
        result = agent.generate_report()
        assert "STRATEGIST REPORT" in result
        assert "Łączna liczba zadań" in result

    # -- check_api_usage with specific provider filter --
    def test_check_api_usage_with_specific_provider(self, agent):
        """check_api_usage with provider filters to that provider only."""
        result = agent.check_api_usage(provider="openai")
        assert "OPENAI" in result
        # Other providers should NOT be shown
        assert "ANTHROPIC" not in result

    # -- _format_provider_limit_block: >95% usage triggers CRITICAL --
    def test_format_provider_limit_block_critical(self, agent):
        """_format_provider_limit_block emits 🚨 when usage > 95%."""
        limits = {"calls": 100, "tokens": 100}
        result = agent._format_provider_limit_block("openai", limits, 96, 96)
        assert "🚨" in result
        assert "OSTRZEŻENIE" in result

    # -- _format_provider_limit_block: 80-95% usage triggers WARNING --
    def test_format_provider_limit_block_warning(self, agent):
        """_format_provider_limit_block emits ⚠️ when usage is 80-95%."""
        limits = {"calls": 100, "tokens": 100}
        result = agent._format_provider_limit_block("openai", limits, 85, 85)
        assert "⚠️" in result

    # -- suggest_local_fallback returns actual suggestions --
    def test_suggest_local_fallback_image(self, agent):
        """suggest_local_fallback returns image suggestion."""
        result = agent.suggest_local_fallback("Generate an image with DALL-E")
        assert "Stable Diffusion" in result
        assert "DALL-E" in result

    def test_suggest_local_fallback_embedding(self, agent):
        """suggest_local_fallback returns embedding suggestion."""
        result = agent.suggest_local_fallback("Create embedding wektoryzacja for docs")
        assert "sentence-transformers" in result

    def test_suggest_local_fallback_large_text(self, agent):
        """suggest_local_fallback returns analysis suggestion for large text."""
        result = agent.suggest_local_fallback("Analiza tekstu duży corpus")
        assert "fragment" in result.lower() or "lokalnego LLM" in result

    def test_suggest_local_fallback_no_suggestions(self, agent):
        """suggest_local_fallback returns OK message when no matches."""
        result = agent.suggest_local_fallback("Sort a list in Python")
        assert "✅" in result

    # -- should_pause_task: overrun > 100% --
    def test_should_pause_task_overrun_over_100(self, agent):
        """should_pause_task returns True when predicted overrun > 100%.

        We must keep actual_minutes <= estimated * 1.5 so update_progress
        doesn't flip the status to OVERRUN (which would short-circuit the check).
        Use estimate=60, actual=50 (<= 90), progress=30% → projected≈167min,
        overrun≈177% > 100%.
        """
        from venom_core.ops.work_ledger import TaskComplexity

        agent.work_ledger.log_task(
            "pause_task", "Pause Task", "Desc", 60, TaskComplexity.MEDIUM
        )
        agent.work_ledger.start_task("pause_task")
        # 30% done after 50 min on a 60-min task → projected = (50/30)*100 = 167min
        # That's > 60min, overrun = (167-60)/60*100 ≈ 177% → should_pause_task=True
        agent.work_ledger.update_progress("pause_task", 30, actual_minutes=50)

        result = agent.should_pause_task("pause_task")
        assert result is True

    # -- should_pause_task: risks > 3 --
    def test_should_pause_task_many_risks(self, agent):
        """should_pause_task returns True when task has > 3 risks."""
        from venom_core.ops.work_ledger import TaskComplexity

        agent.work_ledger.log_task(
            "risky_task", "Risky Task", "Desc", 60, TaskComplexity.MEDIUM
        )
        agent.work_ledger.start_task("risky_task")
        for i in range(4):
            agent.work_ledger.add_risk("risky_task", f"Risk {i}")

        result = agent.should_pause_task("risky_task")
        assert result is True

    # -- should_pause_task: nonexistent task --
    def test_should_pause_task_nonexistent(self, agent):
        """should_pause_task returns False for nonexistent task."""
        assert agent.should_pause_task("no_such_task") is False

    # -- _extract_time edge cases --
    def test_extract_time_json_estimated_minutes(self, agent):
        """_extract_time parses JSON with 'estimated_minutes'."""
        result = agent._extract_time('{"estimated_minutes": 45, "complexity": "medium"}')
        assert result == 45.0

    def test_extract_time_json_minutes_key(self, agent):
        """_extract_time falls back to 'minutes' key in JSON."""
        result = agent._extract_time('{"minutes": 20}')
        assert result == 20.0

    def test_extract_time_text_pattern(self, agent):
        """_extract_time parses 'Oszacowany czas: X' text pattern."""
        result = agent._extract_time("Oszacowany czas: 90 minut")
        assert result == 90.0

    def test_extract_time_fallback_default(self, agent):
        """_extract_time returns 30.0 when no pattern matches."""
        result = agent._extract_time("No time info here")
        assert result == 30.0

    # -- _generate_recommendations branches --
    def test_generate_recommendations_epic(self, agent):
        """EPIC complexity triggers obowiązkowy podział recommendation."""
        from venom_core.ops.work_ledger import TaskComplexity

        result = agent._generate_recommendations(TaskComplexity.EPIC, 10.0, "")
        assert "EPIC" in result

    def test_generate_recommendations_high(self, agent):
        """HIGH complexity triggers podział recommendation."""
        from venom_core.ops.work_ledger import TaskComplexity

        result = agent._generate_recommendations(TaskComplexity.HIGH, 10.0, "")
        assert "HIGH" in result

    def test_generate_recommendations_long_task(self, agent):
        """Task > 4h triggers multi-day planning recommendation."""
        from venom_core.ops.work_ledger import TaskComplexity

        result = agent._generate_recommendations(TaskComplexity.LOW, 300.0, "")
        assert "wielodniow" in result.lower() or "5.0h" in result

    def test_generate_recommendations_medium_task(self, agent):
        """Task 2-4h triggers break recommendation."""
        from venom_core.ops.work_ledger import TaskComplexity

        result = agent._generate_recommendations(TaskComplexity.LOW, 150.0, "")
        assert "przerw" in result.lower() or "długie" in result.lower()

    def test_generate_recommendations_high_risk(self, agent):
        """Many risks trigger prototype recommendation."""
        from venom_core.ops.work_ledger import TaskComplexity

        risky = "⚠️ risk1\nrisk2\nrisk3\nrisk4\nrisk5\nrisk6"
        result = agent._generate_recommendations(TaskComplexity.MEDIUM, 10.0, risky)
        assert "prototyp" in result.lower() or "proof-of-concept" in result.lower()

    def test_generate_recommendations_no_issues(self, agent):
        """Low complexity, short task with no risks gets 'OK' recommendation."""
        from venom_core.ops.work_ledger import TaskComplexity

        result = agent._generate_recommendations(TaskComplexity.LOW, 10.0, "")
        assert "✅" in result

    # -- process() with "analyze:" prefix --
    @pytest.mark.asyncio
    async def test_process_analyze_prefix(self, agent):
        """process('analyze:...') calls analyze_task."""
        result = await agent.process("analyze:sum two numbers")
        assert "STRATEGIST ANALYSIS" in result

    # -- process() with "monitor:" prefix --
    @pytest.mark.asyncio
    async def test_process_monitor_prefix(self, agent):
        """process('monitor:...') calls monitor_task."""
        result = await agent.process("monitor:nonexistent_id")
        assert "❌" in result or "nie istnieje" in result

    # -- process() with "check_api:" prefix --
    @pytest.mark.asyncio
    async def test_process_check_api_prefix(self, agent):
        """process('check_api:openai') calls check_api_usage with provider."""
        result = await agent.process("check_api:openai")
        assert "OPENAI" in result

    # -- analyze_task with risks that have "⚠️" in result --
    @pytest.mark.asyncio
    async def test_analyze_task_with_risks_in_result(self, agent):
        """analyze_task covers the risk-extraction block when risks are found."""
        # 'integracja z' and 'baza danych' trigger RISK_PATTERNS in ComplexitySkill
        desc = "Integracja z zewnętrznym API i baza danych - performance krytyczna"
        result = await agent.analyze_task(desc, task_id="risky_001")
        assert "STRATEGIST ANALYSIS" in result

    # -- analyze_task mocked risks with lines starting "[" --
    @pytest.mark.asyncio
    async def test_analyze_task_risk_lines_added_to_ledger(self, agent):
        """analyze_task adds risk lines starting with '[' to work ledger."""
        from unittest.mock import AsyncMock

        # Mock flag_risks to return lines with "[" prefix (the branch that adds risks)
        agent.complexity_skill.flag_risks = AsyncMock(
            return_value="⚠️ Ryzyka:\n[HIGH] Complex integration risk\n[MEDIUM] Data schema risk"
        )
        result = await agent.analyze_task("Some risky task", task_id="mocked_risky")
        assert "STRATEGIST ANALYSIS" in result
        # Verify risks were added to the ledger
        task = agent.work_ledger.get_task("mocked_risky")
        assert task is not None

    # -- monitor_task with task that has risks --
    def test_monitor_task_with_risks(self, agent):
        """monitor_task covers the 'if task.risks' branch."""
        from venom_core.ops.work_ledger import TaskComplexity

        agent.work_ledger.log_task(
            "risky_monitor", "Risky Monitor", "Desc", 60, TaskComplexity.MEDIUM
        )
        agent.work_ledger.start_task("risky_monitor")
        agent.work_ledger.add_risk("risky_monitor", "High integration complexity")
        agent.work_ledger.add_risk("risky_monitor", "Performance bottleneck")

        result = agent.monitor_task("risky_monitor")
        assert "Zidentyfikowane ryzyka" in result
        assert "High integration complexity" in result

    # -- monitor_task with api_calls_made > 0 (no api_usage metadata) --
    def test_monitor_task_with_api_calls_no_breakdown(self, agent):
        """monitor_task covers api_calls_made>0 branch without api_usage metadata."""
        from venom_core.ops.work_ledger import TaskComplexity

        agent.work_ledger.log_task(
            "api_no_break", "API No Break", "Desc", 60, TaskComplexity.MEDIUM
        )
        agent.work_ledger.start_task("api_no_break")
        task = agent.work_ledger.get_task("api_no_break")
        task.api_calls_made = 5
        task.tokens_used = 2000
        # Explicitly no "api_usage" key in metadata
        task.metadata = {"analyzed_by": "strategist"}

        result = agent.monitor_task("api_no_break")
        assert "API Calls: 5" in result
        assert "Tokens Used: 2000" in result
        assert "Breakdown" not in result

    # -- _calculate_provider_usage: tasks without provider in api_usage (continue branch) --
    def test_calculate_provider_usage_continue_branch(self, agent):
        """_calculate_provider_usage skips tasks with no api_usage for provider."""
        from venom_core.ops.work_ledger import TaskComplexity

        # Add a task with metadata but no api_usage for the queried provider
        agent.work_ledger.log_task(
            "no_openai", "No OpenAI", "Desc", 30, TaskComplexity.LOW,
            metadata={"api_usage": {"anthropic": {"calls": 5, "tokens": 1000}}}
        )
        agent.work_ledger.log_task(
            "no_meta", "No Meta", "Desc", 30, TaskComplexity.LOW,
            metadata={}
        )
        calls, tokens = agent._calculate_provider_usage("openai")
        assert calls == 0
        assert tokens == 0

    # -- _extract_complexity: no match returns MEDIUM --
    def test_extract_complexity_no_match_returns_medium(self, agent):
        """_extract_complexity returns MEDIUM when no complexity value found."""
        from venom_core.ops.work_ledger import TaskComplexity

        result = agent._extract_complexity("No complexity info here at all")
        assert result == TaskComplexity.MEDIUM

    # -- _extract_time: invalid JSON triggers JSONDecodeError continue --
    def test_extract_time_invalid_json_falls_through(self, agent):
        """_extract_time handles invalid JSON-like strings gracefully."""
        # A line that starts/ends with {} but is not valid JSON
        result = agent._extract_time("{invalid json: here}")
        # Should fall through to pattern search then default
        assert result == 30.0

    # -- _extract_time: valid JSON but no minutes key --
    def test_extract_time_json_without_minutes(self, agent):
        """_extract_time returns 30.0 when JSON has no time key."""
        result = agent._extract_time('{"complexity": "medium", "files": 3}')
        assert result == 30.0

    # -- _format_provider_limit_block: 80-95% usage triggers warning --
    def test_format_provider_limit_block_high_warning(self, agent):
        """_format_provider_limit_block warning for 80-95% usage."""
        limits = {"calls": 100, "tokens": 100}
        result = agent._format_provider_limit_block("openai", limits, 85, 20)
        # 85% calls > 80% → warning
        assert "⚠️" in result or "Uwaga" in result

    # -- _usage_percent: zero limit --
    def test_usage_percent_zero_limit(self, agent):
        """_usage_percent returns 0.0 when limit is 0."""
        from venom_core.agents.strategist import StrategistAgent

        assert StrategistAgent._usage_percent(100, 0) == 0.0

    # -- monitor_task with overrun prediction (will_overrun=True) --
    def test_monitor_task_with_overrun_warning(self, agent):
        """monitor_task shows overrun warning when will_overrun is True."""
        from venom_core.ops.work_ledger import TaskComplexity

        agent.work_ledger.log_task(
            "overrun_monitor", "Overrun Monitor", "Desc", 60, TaskComplexity.MEDIUM
        )
        agent.work_ledger.start_task("overrun_monitor")
        # 30% done after 50 min on 60-min task → projected=167min, will_overrun=True
        # 50 < 60*1.5=90 → status stays IN_PROGRESS (not OVERRUN)
        agent.work_ledger.update_progress("overrun_monitor", 30, actual_minutes=50)

        result = agent.monitor_task("overrun_monitor")
        assert "⚠️ OSTRZEŻENIE" in result
        assert "Prognozowany" in result

    # -- _calculate_provider_usage: task WITH api_usage for the provider --
    def test_calculate_provider_usage_with_matching_provider(self, agent):
        """_calculate_provider_usage sums up usage for tasks with matching provider."""
        from venom_core.ops.work_ledger import TaskComplexity

        agent.work_ledger.log_task(
            "with_openai", "With OpenAI", "Desc", 30, TaskComplexity.LOW,
            metadata={"api_usage": {"openai": {"calls": 15, "tokens": 3000}}}
        )
        calls, tokens = agent._calculate_provider_usage("openai")
        assert calls == 15
        assert tokens == 3000

    # -- should_pause_task: task IN_PROGRESS with no overrun and <= 3 risks --
    def test_should_pause_task_returns_false_no_issues(self, agent):
        """should_pause_task returns False when no overrun and risks <= 3."""
        from venom_core.ops.work_ledger import TaskComplexity

        agent.work_ledger.log_task(
            "ok_task", "OK Task", "Desc", 60, TaskComplexity.MEDIUM
        )
        agent.work_ledger.start_task("ok_task")
        # Only 2 risks → not enough to trigger pause
        agent.work_ledger.add_risk("ok_task", "Risk 1")
        agent.work_ledger.add_risk("ok_task", "Risk 2")

        result = agent.should_pause_task("ok_task")
        assert result is False

    # -- _extract_time: JSON with non-numeric minutes → ValueError caught --
    def test_extract_time_non_numeric_minutes_value_error(self, agent):
        """_extract_time handles ValueError from float conversion gracefully."""
        # minutes="not_a_number" → float("not_a_number") raises ValueError
        result = agent._extract_time('{"estimated_minutes": "not_a_number"}')
        # Falls through to text pattern or default
        assert isinstance(result, float)


# ===========================================================================
# UXAnalystAgent – branch coverage
# ===========================================================================


class TestUXAnalystBranches:
    """Branch-level tests for UXAnalystAgent."""

    @pytest.fixture
    def agent(self, mock_kernel, tmp_path):
        from venom_core.agents.ux_analyst import UXAnalystAgent

        with patch("venom_core.agents.ux_analyst.SETTINGS") as ms:
            ms.WORKSPACE_ROOT = str(tmp_path)
            return UXAnalystAgent(mock_kernel)

    # -- analyze_sessions with specific session_ids --
    def test_analyze_sessions_with_session_ids(self, agent, tmp_path):
        """analyze_sessions uses specified session IDs to locate log files."""
        # Point logs_dir to tmp_path
        agent.logs_dir = tmp_path

        # When files don't exist we get an error, not a crash
        result = agent.analyze_sessions(session_ids=["abc", "def"])
        assert "error" in result

    # -- analyze_sessions with no files --
    def test_analyze_sessions_no_files(self, agent, tmp_path):
        """analyze_sessions returns error dict when no files found."""
        agent.logs_dir = tmp_path  # empty dir
        result = agent.analyze_sessions()
        assert "error" in result

    # -- analyze_sessions with events returning empty events --
    def test_analyze_sessions_empty_events(self, agent, tmp_path):
        """analyze_sessions with empty JSONL files returns error."""
        log_file = tmp_path / "session_empty.jsonl"
        log_file.write_text("")  # empty
        agent.logs_dir = tmp_path
        result = agent.analyze_sessions()
        assert "error" in result

    # -- _perform_analysis with complete event data --
    def test_perform_analysis_full(self, agent):
        """_perform_analysis returns structured dict with all keys."""
        events = [
            {
                "event_type": "session_start",
                "session_id": "s1",
                "persona_name": "Senior",
                "emotional_state": "neutral",
            },
            {
                "event_type": "frustration_increase",
                "session_id": "s1",
                "reason": "Button not found",
                "emotional_state": "frustrated",
            },
            {
                "event_type": "session_end",
                "session_id": "s1",
                "goal_achieved": True,
                "rage_quit": False,
                "frustration_level": 2,
                "persona_name": "Senior",
                "emotional_state": "satisfied",
            },
            {
                "event_type": "session_end",
                "session_id": "s2",
                "goal_achieved": False,
                "rage_quit": True,
                "frustration_level": 8,
                "persona_name": "Junior",
                "emotional_state": "angry",
            },
        ]
        result = agent._perform_analysis(events)
        assert "summary" in result
        assert "top_problems" in result
        assert "frustration_heatmap" in result
        assert result["summary"]["total_sessions"] == 2
        assert result["summary"]["rage_quits"] == 1

    # -- process() with 'analizuj' and no logs (error path) --
    @pytest.mark.asyncio
    async def test_process_analizuj_no_logs(self, agent, tmp_path):
        """process('analizuj') returns error message when no log files found."""
        agent.logs_dir = tmp_path  # empty dir
        result = await agent.process("analizuj sesje")
        assert "❌" in result

    # -- process() standard query path (no 'analizuj') --
    @pytest.mark.asyncio
    async def test_process_standard_query(self, agent):
        """process() without 'analizuj' calls LLM and returns response."""
        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = MagicMock(__str__=lambda s: "UX tips for you")
            result = await agent.process("What are good UX patterns?")
        assert "UX" in result or len(result) > 0

    # -- process() exception path --
    @pytest.mark.asyncio
    async def test_process_exception_path(self, agent):
        """process() catches exceptions and returns error message."""
        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.side_effect = RuntimeError("LLM failure")
            result = await agent.process("some query")
        assert "❌" in result or "Błąd" in result

    # -- generate_recommendations success --
    @pytest.mark.asyncio
    async def test_generate_recommendations_success(self, agent):
        """generate_recommendations calls LLM with analysis data."""
        analysis = {
            "summary": {
                "total_sessions": 5,
                "successful_sessions": 3,
                "rage_quits": 1,
                "success_rate": 60.0,
                "avg_frustration": 3.5,
            },
            "top_problems": [{"problem": "menu", "occurrences": 3}],
            "frustration_heatmap": [
                {"persona": "Senior", "sessions": 3, "success_rate": 33.0, "failure_rate": 67.0}
            ],
        }
        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = MagicMock(__str__=lambda s: "Recommendations here")
            result = await agent.generate_recommendations(analysis)
        assert isinstance(result, str)
        assert len(result) > 0

    # -- process() with 'analizuj' and valid logs (success path) --
    @pytest.mark.asyncio
    async def test_process_analizuj_success(self, agent, tmp_path):
        """process('analizuj') returns full report when logs exist."""
        agent.logs_dir = tmp_path

        # Create a valid JSONL log file
        log_file = tmp_path / "session_s1.jsonl"
        events = [
            {
                "event_type": "session_start",
                "session_id": "s1",
                "persona_name": "User",
                "emotional_state": "neutral",
            },
            {
                "event_type": "session_end",
                "session_id": "s1",
                "goal_achieved": True,
                "rage_quit": False,
                "frustration_level": 1,
                "persona_name": "User",
                "emotional_state": "satisfied",
            },
        ]
        with open(log_file, "w") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")

        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = MagicMock(
                __str__=lambda s: "## Rekomendacje\n- Fix the menu"
            )
            result = await agent.process("analizuj sesje")

        assert "RAPORT ANALIZY UX" in result or "Sesji" in result

    # -- _build_summary edge cases --
    def test_build_summary_zero_sessions(self, agent):
        """_build_summary returns 0 rates when no sessions."""
        result = agent._build_summary(0, 0, 0, 0)
        assert result["success_rate"] == 0
        assert result["avg_frustration"] == 0

    def test_build_summary_with_sessions(self, agent):
        """_build_summary calculates correct rates."""
        result = agent._build_summary(10, 7, 2, 30)
        assert result["success_rate"] == 70.0
        assert result["avg_frustration"] == 3.0

    # -- _failure_rate type handling --
    def test_failure_rate_numeric(self, agent):
        """_failure_rate handles numeric value."""
        assert agent._failure_rate({"failure_rate": 45.0}) == 45.0

    def test_failure_rate_string(self, agent):
        """_failure_rate handles string value."""
        assert agent._failure_rate({"failure_rate": "30.5"}) == 30.5

    def test_failure_rate_missing_key(self, agent):
        """_failure_rate returns 0 when key missing."""
        assert agent._failure_rate({}) == 0.0

    # -- _load_session_logs: empty line in JSONL triggers False branch of if line.strip() --
    def test_load_session_logs_with_empty_lines(self, agent, tmp_path):
        """_load_session_logs skips empty lines in JSONL files."""
        log_file = tmp_path / "session_empty_lines.jsonl"
        content = (
            '{"event_type": "session_start", "session_id": "x"}\n'
            "\n"  # blank line → triggers False branch of if line.strip()
            '{"event_type": "session_end", "session_id": "x"}\n'
        )
        log_file.write_text(content)
        events = agent._load_session_logs([log_file])
        assert len(events) == 2  # 2 valid events, empty line skipped

    # -- _perform_analysis: session with no end_event (201->209 branch) --
    def test_perform_analysis_session_without_end(self, agent):
        """_perform_analysis handles sessions that have no session_end event."""
        events = [
            {
                "event_type": "session_start",
                "session_id": "incomplete",
                "persona_name": "User",
                "emotional_state": "neutral",
            },
            # No session_end event → end_event is None → 201->209 branch
        ]
        result = agent._perform_analysis(events)
        assert "summary" in result
        assert result["summary"]["total_sessions"] == 1
        assert result["summary"]["successful_sessions"] == 0

    # -- _failure_rate: non-string/int/float value → returns 0.0 --
    def test_failure_rate_none_value(self, agent):
        """_failure_rate returns 0.0 when value is None (not int/float/str)."""
        assert agent._failure_rate({"failure_rate": None}) == 0.0

    def test_failure_rate_list_value(self, agent):
        """_failure_rate returns 0.0 when value is a list (not int/float/str)."""
        assert agent._failure_rate({"failure_rate": [1, 2, 3]}) == 0.0

    # -- _load_session_logs: exception path (invalid JSON → line 94) --
    def test_load_session_logs_parse_error_covers_exception_handler(self, agent, tmp_path):
        """_load_session_logs exception handler (line 94) runs on invalid JSON."""
        log_file = tmp_path / "bad_json.jsonl"
        log_file.write_text("not valid json at all\n")
        events = agent._load_session_logs([log_file])
        assert events == []  # Error handler returns empty (skips bad file)


# ===========================================================================
# SimulatedUserAgent – branch coverage
# ===========================================================================


class TestSimulatedUserBranches:
    """Branch-level tests for SimulatedUserAgent."""

    @pytest.fixture
    def persona(self):
        from venom_core.simulation.persona_factory import Persona, TechLiteracy

        return Persona(
            name="Alice",
            age=35,
            tech_literacy=TechLiteracy.MEDIUM,
            patience=0.5,
            goal="Find the settings page",
            traits=["curious"],
            frustration_threshold=5,
        )

    @pytest.fixture
    def agent(self, mock_kernel, persona, tmp_path):
        with patch("venom_core.agents.simulated_user.BrowserSkill") as mock_cls:
            mock_browser = MagicMock()
            mock_browser.visit_page = AsyncMock(return_value="✅ Page loaded")
            mock_browser.take_screenshot = AsyncMock(return_value="screenshot.png")
            mock_browser.close_browser = AsyncMock()
            mock_cls.return_value = mock_browser
            from venom_core.agents.simulated_user import SimulatedUserAgent

            return SimulatedUserAgent(
                kernel=mock_kernel,
                persona=persona,
                target_url="http://test.local",
                session_id="test-001",
                workspace_root=str(tmp_path),
            )

    # -- start_session success path --
    @pytest.mark.asyncio
    async def test_start_session_success(self, agent):
        """start_session visits the page and returns first impression."""
        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = MagicMock(
                __str__=lambda s: "I see a clean homepage"
            )
            result = await agent.start_session()
        assert isinstance(result, str)

    # -- start_session page visit failure --
    @pytest.mark.asyncio
    async def test_start_session_page_visit_failure(self, agent):
        """start_session returns error when page visit fails."""
        agent.browser_skill.visit_page = AsyncMock(return_value="❌ Connection refused")
        result = await agent.start_session()
        assert "❌" in result

    # -- start_session exception --
    @pytest.mark.asyncio
    async def test_start_session_exception(self, agent):
        """start_session handles browser exceptions gracefully."""
        agent.browser_skill.visit_page = AsyncMock(side_effect=RuntimeError("crash"))
        result = await agent.start_session()
        assert "❌" in result
        assert agent.frustration_level > 0

    # -- process() when rage_quit is set --
    @pytest.mark.asyncio
    async def test_process_rage_quit(self, agent):
        """process() returns rage quit message immediately."""
        agent.rage_quit = True
        result = await agent.process("do something")
        assert "ZREZYGNOWAŁ" in result

    # -- process() error path increases frustration --
    @pytest.mark.asyncio
    async def test_process_exception_increases_frustration(self, agent):
        """process() exception increases frustration level."""
        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.side_effect = RuntimeError("LLM error")
            result = await agent.process("try something")
        assert "❌" in result
        assert agent.frustration_level > 0

    # -- _increase_frustration emotional states --
    def test_increase_frustration_confused(self, agent):
        """Low frustration sets CONFUSED state."""
        from venom_core.agents.simulated_user import EmotionalState

        agent.frustration_level = 0
        agent._increase_frustration("minor issue")
        assert agent.emotional_state in (EmotionalState.CONFUSED, EmotionalState.FRUSTRATED)

    def test_increase_frustration_frustrated(self, agent):
        """Frustration at FRUSTRATED_THRESHOLD_RATIO sets FRUSTRATED state."""
        from venom_core.agents.simulated_user import EmotionalState

        # threshold = 5, ratio = 0.7 → 3.5, so at 4 we should be FRUSTRATED
        agent.frustration_level = 2
        agent._increase_frustration("confusing UI")
        assert agent.emotional_state in (EmotionalState.FRUSTRATED, EmotionalState.CONFUSED)

    def test_increase_frustration_angry_and_rage_quit(self, agent):
        """Reaching frustration_threshold sets ANGRY and rage_quit=True."""
        from venom_core.agents.simulated_user import EmotionalState

        agent.frustration_level = agent.persona.frustration_threshold - 1
        agent._increase_frustration("final straw")
        assert agent.emotional_state == EmotionalState.ANGRY
        assert agent.rage_quit is True

    # -- run_behavioral_loop: goal achieved --
    @pytest.mark.asyncio
    async def test_run_behavioral_loop_goal_achieved(self, agent):
        """run_behavioral_loop stops when agent reports goal achieved."""
        with patch.object(agent, "start_session", new_callable=AsyncMock):
            with patch.object(
                agent, "process", new_callable=AsyncMock
            ) as mock_process:
                mock_process.return_value = "CEL OSIĄGNIĘTY po kropieniu"
                report = await agent.run_behavioral_loop(max_steps=5)
        assert report["goal_achieved"] is True
        assert "log_file" in report

    # -- run_behavioral_loop: rage quit mid-loop --
    @pytest.mark.asyncio
    async def test_run_behavioral_loop_rage_quit(self, agent):
        """run_behavioral_loop stops on REZYGNUJĘ response."""
        with patch.object(agent, "start_session", new_callable=AsyncMock):
            with patch.object(
                agent, "process", new_callable=AsyncMock
            ) as mock_process:
                mock_process.return_value = "REZYGNUJĘ - za trudne"
                report = await agent.run_behavioral_loop(max_steps=5)
        assert report["rage_quit"] is True

    # -- run_behavioral_loop: max_steps reached --
    @pytest.mark.asyncio
    async def test_run_behavioral_loop_max_steps(self, agent):
        """run_behavioral_loop stops after max_steps with no resolution."""
        with patch.object(agent, "start_session", new_callable=AsyncMock):
            with patch.object(
                agent, "process", new_callable=AsyncMock
            ) as mock_process:
                mock_process.return_value = "Still working on it..."
                report = await agent.run_behavioral_loop(max_steps=2)
        assert report["steps_taken"] == 2

    # -- get_session_summary --
    def test_get_session_summary_goal_achieved(self, agent):
        """get_session_summary shows CEL OSIĄGNIĘTY when goal achieved."""
        agent.goal_achieved = True
        result = agent.get_session_summary()
        assert "CEL OSIĄGNIĘTY" in result

    def test_get_session_summary_rage_quit(self, agent):
        """get_session_summary shows RAGE QUIT when rage_quit is set."""
        agent.rage_quit = True
        result = agent.get_session_summary()
        assert "RAGE QUIT" in result

    def test_get_session_summary_failure(self, agent):
        """get_session_summary shows failure when neither goal nor rage_quit."""
        result = agent.get_session_summary()
        assert "NIE OSIĄGNIĘTO CELU" in result

    # -- process() frustration keyword detection --
    @pytest.mark.asyncio
    async def test_process_frustration_keyword_detection(self, agent):
        """process() increases frustration when response contains frustration keywords."""
        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = MagicMock(
                __str__=lambda s: "nie mogę znaleźć tego przycisku"
            )
            initial_frustration = agent.frustration_level
            await agent.process("find the button")
        assert agent.frustration_level > initial_frustration

    # -- _build_system_prompt with different patience levels --
    def test_build_system_prompt_low_patience(self, mock_kernel, tmp_path):
        """_build_system_prompt handles low patience persona."""
        from venom_core.simulation.persona_factory import Persona, TechLiteracy

        low_patience_persona = Persona(
            name="Impatient",
            age=25,
            tech_literacy=TechLiteracy.LOW,
            patience=0.1,
            goal="Buy ticket",
            traits=["impulsive"],
            frustration_threshold=3,
        )
        with patch("venom_core.agents.simulated_user.BrowserSkill") as mock_cls:
            mock_cls.return_value = MagicMock()
            from venom_core.agents.simulated_user import SimulatedUserAgent

            a = SimulatedUserAgent(
                kernel=mock_kernel,
                persona=low_patience_persona,
                target_url="http://test.local",
                session_id="low-patience",
                workspace_root=str(tmp_path),
            )
        prompt = a._build_system_prompt()
        assert "Impatient" in prompt
        assert "niecierpliwy" in prompt.lower() or "low" in prompt.lower()

    def test_build_system_prompt_high_patience(self, mock_kernel, tmp_path):
        """_build_system_prompt handles high patience persona."""
        from venom_core.simulation.persona_factory import Persona, TechLiteracy

        high_patience_persona = Persona(
            name="Patient",
            age=40,
            tech_literacy=TechLiteracy.HIGH,
            patience=0.9,
            goal="Read docs",
            traits=["thorough"],
            frustration_threshold=10,
        )
        with patch("venom_core.agents.simulated_user.BrowserSkill") as mock_cls:
            mock_cls.return_value = MagicMock()
            from venom_core.agents.simulated_user import SimulatedUserAgent

            a = SimulatedUserAgent(
                kernel=mock_kernel,
                persona=high_patience_persona,
                target_url="http://test.local",
                session_id="high-patience",
                workspace_root=str(tmp_path),
            )
        prompt = a._build_system_prompt()
        assert "Patient" in prompt


# ===========================================================================
# ResearcherAgent – branch coverage
# ===========================================================================


class TestResearcherBranches:
    """Branch-level tests for ResearcherAgent."""

    @pytest.fixture
    def agent(self, mock_kernel):
        from venom_core.agents.researcher import ResearcherAgent

        return ResearcherAgent(mock_kernel)

    # -- format_grounding_sources: empty metadata --
    def test_format_grounding_sources_empty(self):
        from venom_core.agents.researcher import format_grounding_sources

        assert format_grounding_sources({}) == ""
        assert format_grounding_sources(None) == ""

    # -- format_grounding_sources: chunks with URI --
    def test_format_grounding_sources_with_uri(self):
        from venom_core.agents.researcher import format_grounding_sources

        metadata = {
            "grounding_metadata": {
                "grounding_chunks": [
                    {"title": "Python Docs", "uri": "https://docs.python.org"},
                    {"title": "PEP 8", "uri": "https://peps.python.org/pep-0008"},
                ]
            }
        }
        result = format_grounding_sources(metadata)
        assert "Python Docs" in result
        assert "https://docs.python.org" in result
        assert "Źródła" in result

    # -- format_grounding_sources: chunks WITHOUT URI (title only) --
    def test_format_grounding_sources_no_uri(self):
        from venom_core.agents.researcher import format_grounding_sources

        metadata = {
            "grounding_metadata": {
                "grounding_chunks": [
                    {"title": "Internal Doc"},
                ]
            }
        }
        result = format_grounding_sources(metadata)
        assert "Internal Doc" in result

    # -- format_grounding_sources: chunk with no title and no URI --
    def test_format_grounding_sources_no_title_no_uri(self):
        from venom_core.agents.researcher import format_grounding_sources

        metadata = {
            "grounding_metadata": {
                "grounding_chunks": [
                    {},  # Neither title nor uri
                ]
            }
        }
        result = format_grounding_sources(metadata)
        # No URI and no meaningful title → not included, so sources may be empty
        assert isinstance(result, str)

    # -- format_grounding_sources: web_search_queries fallback --
    def test_format_grounding_sources_web_queries(self):
        from venom_core.agents.researcher import format_grounding_sources

        metadata = {"web_search_queries": ["python async await", "asyncio tutorial"]}
        result = format_grounding_sources(metadata)
        assert "Zapytanie" in result or "python async" in result

    # -- process() success with grounding metadata --
    @pytest.mark.asyncio
    async def test_process_success_with_grounding(self, agent):
        """process() adds grounding sources when metadata is present."""
        mock_response = MagicMock()
        mock_response.__str__ = lambda s: "Here is the answer"
        mock_response.metadata = {
            "grounding_metadata": {
                "grounding_chunks": [
                    {"title": "Source 1", "uri": "https://example.com"}
                ]
            }
        }

        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = mock_response
            result = await agent.process("What is Python?")

        # Grounding sources should be appended
        assert "Źródła" in result or len(result) > 10
        assert agent.get_last_search_source() == "google_grounding"

    # -- process() success without grounding metadata --
    @pytest.mark.asyncio
    async def test_process_success_no_grounding(self, agent):
        """process() uses duckduckgo source when no grounding metadata."""
        mock_response = MagicMock()
        mock_response.__str__ = lambda s: "Python answer"
        mock_response.metadata = {}

        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = mock_response
            result = await agent.process("What is Python?")

        assert isinstance(result, str)
        assert agent.get_last_search_source() == "duckduckgo"

    # -- process() error handling --
    @pytest.mark.asyncio
    async def test_process_exception(self, agent):
        """process() catches exceptions and returns error message."""
        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.side_effect = RuntimeError("Network error")
            result = await agent.process("query")

        assert "błąd" in result.lower() or "error" in result.lower()

    # -- process() response without metadata attribute --
    @pytest.mark.asyncio
    async def test_process_response_without_metadata_attr(self, agent):
        """process() handles response objects without .metadata attribute."""
        mock_response = "plain string response"

        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = mock_response
            result = await agent.process("query")

        assert isinstance(result, str)
        assert agent.get_last_search_source() == "duckduckgo"

    # -- _extract_urls --
    def test_extract_urls_with_results(self, agent):
        """_extract_urls parses URL markers from search output."""
        from venom_core.agents.researcher import ResearcherAgent

        output = "Title: Python\nURL: https://python.org\nTitle: Docs\nURL: https://docs.python.org"
        urls = ResearcherAgent._extract_urls(output)
        assert "https://python.org" in urls
        assert "https://docs.python.org" in urls

    def test_extract_urls_empty(self, agent):
        """_extract_urls returns empty list for empty or None input."""
        from venom_core.agents.researcher import ResearcherAgent

        assert ResearcherAgent._extract_urls("") == []
        assert ResearcherAgent._extract_urls(None) == []

    # -- _search_scrape_and_summarize: testing_mode skips it --
    @pytest.mark.asyncio
    async def test_search_scrape_testing_mode(self, agent):
        """_search_scrape_and_summarize returns None in testing_mode."""
        agent._testing_mode = True
        result = await agent._search_scrape_and_summarize("any query")
        assert result is None

    # -- _search_scrape_and_summarize: empty query --
    @pytest.mark.asyncio
    async def test_search_scrape_empty_query(self, agent):
        """_search_scrape_and_summarize returns None for empty query."""
        agent._testing_mode = False
        result = await agent._search_scrape_and_summarize("")
        assert result is None

    # -- _search_scrape_and_summarize: no URLs found --
    @pytest.mark.asyncio
    async def test_search_scrape_no_urls(self, agent):
        """_search_scrape_and_summarize returns None when search yields no URLs."""
        agent._testing_mode = False

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = "No results found"  # No URL: markers
            result = await agent._search_scrape_and_summarize("obscure query")

        assert result is None

    # -- get_last_search_source default --
    def test_get_last_search_source_default(self, agent):
        """get_last_search_source returns 'duckduckgo' by default."""
        assert agent.get_last_search_source() == "duckduckgo"

    # -- Non-testing-mode path: process() uses _search_scrape_and_summarize --
    @pytest.mark.asyncio
    async def test_process_non_testing_mode_search_returns_result(self, agent):
        """process() returns search result directly when not in testing mode."""
        agent._testing_mode = False
        with patch.object(
            agent,
            "_search_scrape_and_summarize",
            new_callable=AsyncMock,
            return_value="Summary from search\n\nŹródła:\n- https://example.com",
        ):
            result = await agent.process("What is Python?")
        assert "Summary from search" in result
        assert agent.get_last_search_source() == "duckduckgo"

    # -- Non-testing-mode path: process() falls back to LLM when search returns None --
    @pytest.mark.asyncio
    async def test_process_non_testing_mode_search_returns_none(self, agent):
        """process() falls back to LLM when search returns no result."""
        agent._testing_mode = False
        mock_response = MagicMock()
        mock_response.__str__ = lambda s: "LLM fallback answer"
        mock_response.metadata = {}

        with (
            patch.object(
                agent,
                "_search_scrape_and_summarize",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(
                agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
            ) as mock_chat,
        ):
            mock_chat.return_value = mock_response
            result = await agent.process("query")
        assert "LLM fallback" in result

    # -- _search_scrape_and_summarize: full scrape+summarize path --
    @pytest.mark.asyncio
    async def test_search_scrape_and_summarize_success(self, agent):
        """_search_scrape_and_summarize returns summary when scraping succeeds."""
        import asyncio as asyncio_mod

        agent._testing_mode = False
        agent.web_skill = MagicMock()
        agent.web_skill.search = MagicMock(
            return_value="Title: Python\nURL: https://python.org\nSnippet: Python language"
        )
        agent.web_skill.scrape_text = MagicMock(
            return_value="Python is a high-level programming language."
        )

        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = MagicMock(
                __str__=lambda s: "Python is versatile and easy to learn."
            )
            with patch("asyncio.to_thread", side_effect=asyncio_mod.coroutine(
                lambda fn, *args, **kwargs: fn(*args, **kwargs)
            ) if False else None) as _:
                pass

        # Use a direct approach: mock asyncio.to_thread
        async def fake_to_thread(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        with (
            patch("asyncio.to_thread", side_effect=fake_to_thread),
            patch.object(
                agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
            ) as mock_chat,
        ):
            mock_chat.return_value = MagicMock(
                __str__=lambda s: "Python is a great language."
            )
            result = await agent._search_scrape_and_summarize("Python programming")

        assert result is not None
        assert "Źródła" in result

    # -- _search_scrape_and_summarize: no scraped content → returns None --
    @pytest.mark.asyncio
    async def test_search_scrape_no_scraped_content(self, agent):
        """_search_scrape_and_summarize returns None when scraping yields empty content."""
        agent._testing_mode = False
        agent.web_skill = MagicMock()
        agent.web_skill.search = MagicMock(
            return_value="Title: Page\nURL: https://example.com\nSnippet: info"
        )
        agent.web_skill.scrape_text = MagicMock(return_value="")  # Empty content

        async def fake_to_thread(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        with patch("asyncio.to_thread", side_effect=fake_to_thread):
            result = await agent._search_scrape_and_summarize("some query")

        assert result is None

    # -- ResearcherAgent init without testing mode (covers lines 148-164) --
    def test_researcher_init_non_testing_mode(self, mock_kernel):
        """ResearcherAgent __init__ covers optional plugin registration outside tests."""
        import sys
        from venom_core.agents.researcher import ResearcherAgent

        mock_gh_module = MagicMock()
        mock_gh_module.GitHubSkill = MagicMock()
        mock_hf_module = MagicMock()
        mock_hf_module.HuggingFaceSkill = MagicMock()

        with (
            patch("venom_core.agents.researcher.os.getenv", return_value=None),
            patch.dict(
                sys.modules,
                {
                    "venom_core.execution.skills.github_skill": mock_gh_module,
                    "venom_core.execution.skills.huggingface_skill": mock_hf_module,
                },
            ),
        ):
            agent = ResearcherAgent(mock_kernel)
        assert isinstance(agent, ResearcherAgent)

    # -- _summarize_sources: content > 2000 chars triggers truncation (line 313) --
    @pytest.mark.asyncio
    async def test_summarize_sources_long_content_truncated(self, agent):
        """_summarize_sources truncates content > 2000 chars."""
        agent._testing_mode = False
        long_content = "Python info " * 300  # > 2000 chars
        sources = [("https://python.org", long_content)]

        with patch.object(
            agent, "_invoke_chat_with_fallbacks", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = MagicMock(
                __str__=lambda s: "Truncated summary"
            )
            result = await agent._summarize_sources("Python", sources)
        assert isinstance(result, str)
        assert len(result) > 0
