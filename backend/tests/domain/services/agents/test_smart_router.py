"""
Unit tests for SmartRouter, RoutingResult, RouteDecision, ResponseValidator,
and the module-level helpers get_smart_router() / try_bypass_llm().

Tests cover:
- RouteDecision enum values
- RoutingResult dataclass defaults and field assignment
- SmartRouter.route: empty, ambiguous, completion, greetings, thanks, farewells,
  identity, model questions, file/search/shell direct tool patterns, complex → NEEDS_LLM,
  disabled options (direct_responses, direct_tools), whitespace-only input
- SmartRouter.check_early_termination: completion signals with few/many steps, error
  signals, normal result, empty result
- SmartRouter.select_tool_by_task: multiple matches, single match (below threshold),
  unavailable tool, no keywords
- SmartRouter.format_template_response: all built-in templates, missing template key,
  missing required variable
- SmartRouter statistics: increment on each route path, bypass_rate formula,
  estimated_cost_savings, reset_stats clears all counters
- ResponseValidator.is_valid_file_path: valid paths, empty string, disallowed characters
- ResponseValidator.is_valid_url: http/https, localhost, IP, no-scheme, ftp (rejected)
- ResponseValidator.is_valid_json: valid objects/arrays, primitives, malformed JSON
- ResponseValidator.extract_code_blocks: fenced code blocks with and without language,
  multiple blocks, no blocks present
- Singleton: get_smart_router returns same instance; try_bypass_llm delegates to it
"""

import pytest

import app.domain.services.agents.smart_router as smart_router_module
from app.domain.services.agents.smart_router import (
    ResponseValidator,
    RouteDecision,
    RoutingResult,
    SmartRouter,
    get_smart_router,
    try_bypass_llm,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture()
def router() -> SmartRouter:
    """Fresh SmartRouter with default options."""
    return SmartRouter()


@pytest.fixture()
def router_no_direct() -> SmartRouter:
    """SmartRouter with both direct response and tool bypasses disabled."""
    return SmartRouter(enable_direct_responses=False, enable_direct_tools=False)


@pytest.fixture()
def router_no_responses() -> SmartRouter:
    """SmartRouter with direct response bypass disabled but tools enabled."""
    return SmartRouter(enable_direct_responses=False, enable_direct_tools=True)


@pytest.fixture()
def router_no_tools() -> SmartRouter:
    """SmartRouter with tool bypass disabled but direct responses enabled."""
    return SmartRouter(enable_direct_responses=True, enable_direct_tools=False)


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the module-level singleton before each test to avoid cross-test pollution."""
    smart_router_module._router = None
    yield
    smart_router_module._router = None


# ============================================================================
# Test Class 1: RouteDecision Enum
# ============================================================================


class TestRouteDecision:
    """RouteDecision enum values and string representation."""

    def test_all_members_exist(self):
        assert RouteDecision.NEEDS_LLM
        assert RouteDecision.DIRECT_RESPONSE
        assert RouteDecision.TOOL_CALL
        assert RouteDecision.CLARIFICATION
        assert RouteDecision.EARLY_TERMINATE
        assert RouteDecision.ERROR

    def test_string_values(self):
        assert RouteDecision.NEEDS_LLM == "needs_llm"
        assert RouteDecision.DIRECT_RESPONSE == "direct_response"
        assert RouteDecision.TOOL_CALL == "tool_call"
        assert RouteDecision.CLARIFICATION == "clarification"
        assert RouteDecision.EARLY_TERMINATE == "early_terminate"
        assert RouteDecision.ERROR == "error"

    def test_is_str_subclass(self):
        assert isinstance(RouteDecision.NEEDS_LLM, str)


# ============================================================================
# Test Class 2: RoutingResult Dataclass
# ============================================================================


class TestRoutingResult:
    """RoutingResult dataclass defaults and field assignment."""

    def test_minimal_construction(self):
        result = RoutingResult(decision=RouteDecision.NEEDS_LLM)
        assert result.decision == RouteDecision.NEEDS_LLM
        assert result.response is None
        assert result.tool_name is None
        assert result.tool_args is None
        assert result.confidence == 1.0
        assert result.reason == ""
        assert result.bypass_llm is False

    def test_full_construction(self):
        result = RoutingResult(
            decision=RouteDecision.TOOL_CALL,
            response="some response",
            tool_name="file_read",
            tool_args={"path": "/tmp/file.txt"},
            confidence=0.9,
            reason="direct match",
            bypass_llm=True,
        )
        assert result.decision == RouteDecision.TOOL_CALL
        assert result.response == "some response"
        assert result.tool_name == "file_read"
        assert result.tool_args == {"path": "/tmp/file.txt"}
        assert result.confidence == 0.9
        assert result.reason == "direct match"
        assert result.bypass_llm is True


# ============================================================================
# Test Class 3: SmartRouter.route — Clarification
# ============================================================================


class TestRouteReturnsClarification:
    """Empty and ambiguous inputs produce CLARIFICATION."""

    def test_empty_string_returns_clarification(self, router: SmartRouter):
        result = router.route("")
        assert result.decision == RouteDecision.CLARIFICATION
        assert result.reason == "Empty message"

    def test_whitespace_only_strips_and_checks_patterns(self, router: SmartRouter):
        # "   " strips to "" — ambiguous patterns won't match but the
        # stripped-empty path isn't hit because the guard only fires on falsy
        # original. Whitespace-only is a single character class; after strip it
        # becomes "" → still not empty-str early guard, but "   ".strip() == ""
        # Actually the code does `message.strip()` AFTER the empty guard, so "  "
        # passes the empty guard, then after strip becomes "", then nothing matches
        # → NEEDS_LLM.  Test that behaviour (no crash, valid decision returned).
        result = router.route("   ")
        assert result.decision in {
            RouteDecision.CLARIFICATION,
            RouteDecision.NEEDS_LLM,
        }

    def test_single_vague_word_it(self, router: SmartRouter):
        result = router.route("it")
        assert result.decision == RouteDecision.CLARIFICATION
        assert result.bypass_llm is True

    def test_single_vague_word_this(self, router: SmartRouter):
        result = router.route("this")
        assert result.decision == RouteDecision.CLARIFICATION

    def test_single_vague_word_that(self, router: SmartRouter):
        result = router.route("that")
        assert result.decision == RouteDecision.CLARIFICATION

    def test_only_question_marks(self, router: SmartRouter):
        result = router.route("???")
        assert result.decision == RouteDecision.CLARIFICATION

    def test_single_question_mark(self, router: SmartRouter):
        result = router.route("?")
        assert result.decision == RouteDecision.CLARIFICATION

    def test_single_letter(self, router: SmartRouter):
        result = router.route("a")
        assert result.decision == RouteDecision.CLARIFICATION

    def test_two_letters(self, router: SmartRouter):
        result = router.route("ok")
        assert result.decision == RouteDecision.CLARIFICATION


# ============================================================================
# Test Class 4: SmartRouter.route — Early Termination
# ============================================================================


class TestRouteReturnsEarlyTerminate:
    """Completion signals produce EARLY_TERMINATE."""

    def test_done_message(self, router: SmartRouter):
        result = router.route("done")
        assert result.decision == RouteDecision.EARLY_TERMINATE
        assert result.bypass_llm is True

    def test_finished_message(self, router: SmartRouter):
        result = router.route("I'm finished")
        assert result.decision == RouteDecision.EARLY_TERMINATE

    def test_completed_keyword(self, router: SmartRouter):
        result = router.route("completed")
        assert result.decision == RouteDecision.EARLY_TERMINATE

    def test_all_set_message(self, router: SmartRouter):
        result = router.route("all set!")
        assert result.decision == RouteDecision.EARLY_TERMINATE

    def test_thats_all(self, router: SmartRouter):
        result = router.route("that's all")
        assert result.decision == RouteDecision.EARLY_TERMINATE

    def test_nothing_else(self, router: SmartRouter):
        result = router.route("nothing else")
        assert result.decision == RouteDecision.EARLY_TERMINATE

    def test_no_thanks(self, router: SmartRouter):
        result = router.route("no thanks")
        assert result.decision == RouteDecision.EARLY_TERMINATE

    def test_early_terminate_increments_stat(self, router: SmartRouter):
        router.route("done")
        stats = router.get_stats()
        assert stats["early_terminations"] == 1


# ============================================================================
# Test Class 5: SmartRouter.route — Direct Responses
# ============================================================================


class TestRouteReturnsDirectResponse:
    """Greeting / farewell / identity patterns return DIRECT_RESPONSE."""

    def test_hi_greeting_is_ambiguous(self, router: SmartRouter):
        # "hi" is two lowercase letters and matches ^[a-z]{1,2}$ AMBIGUOUS_PATTERNS,
        # which is checked before DIRECT_RESPONSE_PATTERNS in route().
        # The ambiguous guard fires first, yielding CLARIFICATION.
        result = router.route("hi")
        assert result.decision == RouteDecision.CLARIFICATION
        assert result.bypass_llm is True

    def test_hello_greeting(self, router: SmartRouter):
        result = router.route("hello")
        assert result.decision == RouteDecision.DIRECT_RESPONSE

    def test_hello_with_exclamation(self, router: SmartRouter):
        result = router.route("hello!")
        assert result.decision == RouteDecision.DIRECT_RESPONSE

    def test_hey_greeting(self, router: SmartRouter):
        result = router.route("hey")
        assert result.decision == RouteDecision.DIRECT_RESPONSE

    def test_thanks(self, router: SmartRouter):
        result = router.route("thanks")
        assert result.decision == RouteDecision.DIRECT_RESPONSE
        assert "welcome" in (result.response or "").lower()

    def test_thank_you(self, router: SmartRouter):
        result = router.route("thank you")
        assert result.decision == RouteDecision.DIRECT_RESPONSE

    def test_goodbye(self, router: SmartRouter):
        result = router.route("bye")
        assert result.decision == RouteDecision.DIRECT_RESPONSE
        assert "Goodbye" in (result.response or "")

    def test_who_are_you_returns_identity(self, router: SmartRouter):
        result = router.route("who are you")
        assert result.decision == RouteDecision.DIRECT_RESPONSE
        assert "Pythinker" in (result.response or "")

    def test_who_are_you_with_question_mark(self, router: SmartRouter):
        result = router.route("who are you?")
        assert result.decision == RouteDecision.DIRECT_RESPONSE
        assert "Pythinker" in (result.response or "")

    def test_what_are_you(self, router: SmartRouter):
        result = router.route("what are you?")
        assert result.decision == RouteDecision.DIRECT_RESPONSE
        assert "Pythinker" in (result.response or "")

    def test_who_created_you(self, router: SmartRouter):
        result = router.route("who created you?")
        assert result.decision == RouteDecision.DIRECT_RESPONSE
        assert "Mohamed Elkholy" in (result.response or "")

    def test_who_made_you(self, router: SmartRouter):
        result = router.route("who made you?")
        assert result.decision == RouteDecision.DIRECT_RESPONSE

    def test_what_is_your_model(self, router: SmartRouter):
        result = router.route("what's your model?")
        assert result.decision == RouteDecision.DIRECT_RESPONSE
        assert "Pythinker" in (result.response or "")
        # Model response should NOT reveal backend model name
        assert "Mohamed Elkholy" in (result.response or "")

    def test_what_model_are_you(self, router: SmartRouter):
        result = router.route("what model are you?")
        assert result.decision == RouteDecision.DIRECT_RESPONSE

    def test_which_model_powers_you(self, router: SmartRouter):
        result = router.route("which model powers you?")
        assert result.decision == RouteDecision.DIRECT_RESPONSE

    def test_direct_response_disabled_falls_to_needs_llm(self, router_no_responses: SmartRouter):
        result = router_no_responses.route("who are you?")
        assert result.decision == RouteDecision.NEEDS_LLM
        assert result.bypass_llm is False

    def test_direct_response_increments_stats(self, router: SmartRouter):
        router.route("hello")
        stats = router.get_stats()
        assert stats["direct_responses"] == 1
        assert stats["llm_bypassed"] == 1


# ============================================================================
# Test Class 6: SmartRouter.route — Direct Tool Calls
# ============================================================================


class TestRouteReturnsToolCall:
    """Direct tool patterns return TOOL_CALL with correct args."""

    def test_read_file_absolute_path(self, router: SmartRouter):
        result = router.route("read /tmp/test.txt")
        assert result.decision == RouteDecision.TOOL_CALL
        assert result.tool_name == "file_read"
        assert result.tool_args == {"path": "/tmp/test.txt"}
        assert result.bypass_llm is True

    def test_show_file(self, router: SmartRouter):
        result = router.route("show /etc/hosts")
        assert result.decision == RouteDecision.TOOL_CALL
        assert result.tool_name == "file_read"

    def test_cat_file(self, router: SmartRouter):
        result = router.route("cat /var/log/app.log")
        assert result.decision == RouteDecision.TOOL_CALL
        assert result.tool_name == "file_read"

    def test_list_directory(self, router: SmartRouter):
        result = router.route("list /home/user")
        assert result.decision == RouteDecision.TOOL_CALL
        assert result.tool_name == "file_list"
        assert result.tool_args == {"path": "/home/user"}

    def test_ls_directory(self, router: SmartRouter):
        result = router.route("ls /tmp")
        assert result.decision == RouteDecision.TOOL_CALL
        assert result.tool_name == "file_list"

    def test_run_shell_command(self, router: SmartRouter):
        result = router.route("run ls -la")
        assert result.decision == RouteDecision.TOOL_CALL
        assert result.tool_name == "shell_exec"
        assert result.tool_args == {"command": "ls -la"}

    def test_execute_command(self, router: SmartRouter):
        result = router.route("execute pwd")
        assert result.decision == RouteDecision.TOOL_CALL
        assert result.tool_name == "shell_exec"

    def test_search_for_cats(self, router: SmartRouter):
        result = router.route("search for cats")
        assert result.decision == RouteDecision.TOOL_CALL
        assert result.tool_name == "info_search_web"
        assert result.tool_args == {"query": "cats"}

    def test_google_query(self, router: SmartRouter):
        result = router.route("google python asyncio")
        assert result.decision == RouteDecision.TOOL_CALL
        assert result.tool_name == "info_search_web"
        assert result.tool_args == {"query": "python asyncio"}

    def test_tool_call_increments_stats(self, router: SmartRouter):
        router.route("search for dogs")
        stats = router.get_stats()
        assert stats["direct_tools"] == 1
        assert stats["llm_bypassed"] == 1

    def test_direct_tools_disabled_falls_to_needs_llm(self, router_no_tools: SmartRouter):
        result = router_no_tools.route("search for cats")
        assert result.decision == RouteDecision.NEEDS_LLM
        assert result.bypass_llm is False

    def test_both_disabled_always_needs_llm(self, router_no_direct: SmartRouter):
        # "hi" is 2 chars → matched as ambiguous (CLARIFICATION) before direct response
        # Use longer messages that would normally hit direct patterns
        for msg in ("search for python", "read /tmp/a.txt"):
            result = router_no_direct.route(msg)
            assert result.decision == RouteDecision.NEEDS_LLM, f"Expected NEEDS_LLM for: {msg!r}"


# ============================================================================
# Test Class 7: SmartRouter.route — Complex → NEEDS_LLM
# ============================================================================


class TestRouteReturnsNeedsLlm:
    """Complex messages that match no fast-path return NEEDS_LLM."""

    def test_complex_coding_question(self, router: SmartRouter):
        result = router.route("Can you implement a Python class that inherits from ABC and uses generics?")
        assert result.decision == RouteDecision.NEEDS_LLM
        assert result.bypass_llm is False

    def test_arbitrary_sentence(self, router: SmartRouter):
        result = router.route("Explain the difference between threads and processes in Python.")
        assert result.decision == RouteDecision.NEEDS_LLM

    def test_total_routes_incremented_for_needs_llm(self, router: SmartRouter):
        router.route("tell me a joke")
        stats = router.get_stats()
        assert stats["total_routes"] == 1


# ============================================================================
# Test Class 8: SmartRouter.check_early_termination
# ============================================================================


class TestCheckEarlyTermination:
    """check_early_termination logic."""

    def test_completion_signal_with_few_remaining_steps_terminates(self, router: SmartRouter):
        should_stop, reason = router.check_early_termination(
            step_result="Task completed successfully.",
            remaining_steps=1,
            user_goal="write a file",
        )
        assert should_stop is True
        assert reason is not None
        assert "task completed" in reason.lower() or "completion" in reason.lower()

    def test_completion_signal_with_many_steps_does_not_terminate(self, router: SmartRouter):
        # remaining_steps=5 > threshold of 2 → should NOT terminate
        should_stop, reason = router.check_early_termination(
            step_result="Task completed successfully.",
            remaining_steps=5,
            user_goal="write a file",
        )
        assert should_stop is False
        assert reason is None

    def test_file_saved_signal_with_zero_remaining_terminates(self, router: SmartRouter):
        should_stop, _reason = router.check_early_termination(
            step_result="file saved to /tmp/output.txt",
            remaining_steps=0,
            user_goal="save a file",
        )
        assert should_stop is True

    def test_done_signal_with_two_remaining_terminates(self, router: SmartRouter):
        should_stop, _reason = router.check_early_termination(
            step_result="All done.",
            remaining_steps=2,
            user_goal="do something",
        )
        assert should_stop is True

    def test_error_permission_denied_terminates(self, router: SmartRouter):
        should_stop, reason = router.check_early_termination(
            step_result="Error: permission denied for /etc/shadow",
            remaining_steps=10,
            user_goal="read secure file",
        )
        assert should_stop is True
        assert reason is not None
        assert "permission denied" in reason.lower()

    def test_error_file_not_found_terminates(self, router: SmartRouter):
        should_stop, reason = router.check_early_termination(
            step_result="file not found at /missing/path",
            remaining_steps=3,
            user_goal="read file",
        )
        assert should_stop is True
        assert "file not found" in (reason or "").lower()

    def test_error_connection_refused_terminates(self, router: SmartRouter):
        should_stop, _reason = router.check_early_termination(
            step_result="connection refused to localhost:5432",
            remaining_steps=2,
            user_goal="query db",
        )
        assert should_stop is True

    def test_error_authentication_failed_terminates(self, router: SmartRouter):
        should_stop, _reason = router.check_early_termination(
            step_result="authentication failed for user admin",
            remaining_steps=1,
            user_goal="login",
        )
        assert should_stop is True

    def test_normal_result_does_not_terminate(self, router: SmartRouter):
        should_stop, reason = router.check_early_termination(
            step_result="Fetched 10 records from the database.",
            remaining_steps=3,
            user_goal="fetch records",
        )
        assert should_stop is False
        assert reason is None

    def test_empty_step_result_returns_false(self, router: SmartRouter):
        should_stop, reason = router.check_early_termination(
            step_result="",
            remaining_steps=2,
            user_goal="anything",
        )
        assert should_stop is False
        assert reason is None


# ============================================================================
# Test Class 9: SmartRouter.select_tool_by_task
# ============================================================================


class TestSelectToolByTask:
    """select_tool_by_task rule-based selection."""

    def test_multiple_read_keywords_matches_file_read(self, router: SmartRouter):
        # "read" and "contents of" are both in file_read keywords → score=2
        tool = router.select_tool_by_task(
            "read the contents of the file",
            available_tools=["file_read", "file_list"],
        )
        assert tool == "file_read"

    def test_multiple_search_keywords_matches_search(self, router: SmartRouter):
        # "search" and "find online" and "look up" are in info_search_web keywords
        tool = router.select_tool_by_task(
            "search and look up python tutorials online",
            available_tools=["info_search_web", "file_read"],
        )
        assert tool == "info_search_web"

    def test_single_keyword_below_threshold_returns_none(self, router: SmartRouter):
        # Only "read" matches file_read → score=1 → below threshold of 2
        tool = router.select_tool_by_task(
            "read it",
            available_tools=["file_read"],
        )
        assert tool is None

    def test_unavailable_tool_not_returned(self, router: SmartRouter):
        # "search" + "look up" → score=2 for info_search_web, but it's not available
        tool = router.select_tool_by_task(
            "search and look up python",
            available_tools=["file_read", "browsing"],
        )
        assert tool != "info_search_web"

    def test_empty_available_tools_returns_none(self, router: SmartRouter):
        tool = router.select_tool_by_task("read the contents of config", available_tools=[])
        assert tool is None

    def test_no_matching_keywords_returns_none(self, router: SmartRouter):
        tool = router.select_tool_by_task(
            "calculate the fibonacci sequence",
            available_tools=["file_read", "info_search_web"],
        )
        assert tool is None

    def test_shell_exec_multi_keyword_match(self, router: SmartRouter):
        # "run command" and "execute" and "bash" → all in shell_exec keywords
        tool = router.select_tool_by_task(
            "run command execute a bash script",
            available_tools=["shell_exec"],
        )
        assert tool == "shell_exec"


# ============================================================================
# Test Class 10: SmartRouter.format_template_response
# ============================================================================


class TestFormatTemplateResponse:
    """format_template_response with built-in templates."""

    def test_file_created_template(self, router: SmartRouter):
        result = router.format_template_response("file_created", path="/tmp/out.txt")
        assert result == "Successfully created file: /tmp/out.txt"

    def test_file_read_template(self, router: SmartRouter):
        result = router.format_template_response("file_read", path="/tmp/a.txt", content="hello")
        assert result == "Here's the content of /tmp/a.txt:\n\nhello"

    def test_search_results_template(self, router: SmartRouter):
        result = router.format_template_response(
            "search_results", count=3, query="cats", results="- cat1\n- cat2\n- cat3"
        )
        assert "Found 3 results for 'cats'" in result
        assert "cat1" in result

    def test_error_file_not_found_template(self, router: SmartRouter):
        result = router.format_template_response("error_file_not_found", path="/missing.txt")
        assert result == "The file '/missing.txt' was not found."

    def test_error_permission_template(self, router: SmartRouter):
        result = router.format_template_response("error_permission", path="/etc/shadow")
        assert result == "Permission denied for '/etc/shadow'."

    def test_step_complete_template(self, router: SmartRouter):
        result = router.format_template_response("step_complete", description="fetch data")
        assert result == "Step completed: fetch data"

    def test_task_complete_template(self, router: SmartRouter):
        result = router.format_template_response("task_complete", summary="All steps done.")
        assert "Task completed successfully" in result
        assert "All steps done." in result

    def test_unknown_template_key_returns_none(self, router: SmartRouter):
        result = router.format_template_response("nonexistent_key", foo="bar")
        assert result is None

    def test_missing_variable_returns_none(self, router: SmartRouter):
        # file_created requires {path}, omitting it → KeyError → returns None
        result = router.format_template_response("file_created")
        assert result is None


# ============================================================================
# Test Class 11: SmartRouter Statistics
# ============================================================================


class TestSmartRouterStats:
    """Statistics tracking and reset."""

    def test_initial_stats_all_zero(self, router: SmartRouter):
        stats = router.get_stats()
        assert stats["total_routes"] == 0
        assert stats["llm_bypassed"] == 0
        assert stats["direct_responses"] == 0
        assert stats["direct_tools"] == 0
        assert stats["early_terminations"] == 0

    def test_total_routes_increments_on_every_call(self, router: SmartRouter):
        router.route("hello")
        router.route("bye")
        router.route("complex reasoning task here")
        assert router.get_stats()["total_routes"] == 3

    def test_bypass_rate_zero_when_no_routes(self, router: SmartRouter):
        stats = router.get_stats()
        assert stats["bypass_rate"] == "0.0%"

    def test_bypass_rate_100_percent_when_all_bypassed(self, router: SmartRouter):
        router.route("hello!")  # direct response (greeting)
        router.route("thanks!")  # direct response (thanks)
        stats = router.get_stats()
        assert stats["bypass_rate"] == "100.0%"

    def test_bypass_rate_formula(self, router: SmartRouter):
        router.route("hello!")  # bypassed (direct response)
        router.route("thanks!")  # bypassed (direct response)
        router.route("explain AI")  # not bypassed (NEEDS_LLM)
        stats = router.get_stats()
        # 2 bypassed / 3 total = 66.7%
        assert stats["bypass_rate"] == "66.7%"

    def test_estimated_cost_savings_present(self, router: SmartRouter):
        router.route("hello")
        stats = router.get_stats()
        assert "estimated_cost_savings" in stats
        assert "USD" in stats["estimated_cost_savings"]

    def test_reset_stats_clears_all_counters(self, router: SmartRouter):
        router.route("hello")
        router.route("thanks")
        router.route("done")
        router.reset_stats()
        stats = router.get_stats()
        assert stats["total_routes"] == 0
        assert stats["llm_bypassed"] == 0
        assert stats["direct_responses"] == 0
        assert stats["direct_tools"] == 0
        assert stats["early_terminations"] == 0

    def test_reset_stats_bypass_rate_resets_to_zero(self, router: SmartRouter):
        router.route("hello")
        router.reset_stats()
        assert router.get_stats()["bypass_rate"] == "0.0%"


# ============================================================================
# Test Class 12: ResponseValidator.is_valid_file_path
# ============================================================================


class TestResponseValidatorFilePath:
    """is_valid_file_path validation."""

    def test_absolute_unix_path_is_valid(self):
        assert ResponseValidator.is_valid_file_path("/tmp/test.txt") is True

    def test_relative_path_is_valid(self):
        assert ResponseValidator.is_valid_file_path("relative/path/file.py") is True

    def test_dot_slash_path_is_valid(self):
        assert ResponseValidator.is_valid_file_path("./file.txt") is True

    def test_path_with_spaces_is_valid(self):
        # Spaces are not in the disallowed set
        assert ResponseValidator.is_valid_file_path("/tmp/my file.txt") is True

    def test_empty_string_is_invalid(self):
        assert ResponseValidator.is_valid_file_path("") is False

    def test_path_with_null_byte_is_invalid(self):
        assert ResponseValidator.is_valid_file_path("/tmp/bad\0path") is False

    def test_path_with_angle_bracket_is_invalid(self):
        assert ResponseValidator.is_valid_file_path("/tmp/<badpath>") is False

    def test_path_with_pipe_is_invalid(self):
        assert ResponseValidator.is_valid_file_path("/tmp/file|cmd") is False


# ============================================================================
# Test Class 13: ResponseValidator.is_valid_url
# ============================================================================


class TestResponseValidatorUrl:
    """is_valid_url validation."""

    def test_https_url_is_valid(self):
        assert ResponseValidator.is_valid_url("https://example.com") is True

    def test_http_url_is_valid(self):
        assert ResponseValidator.is_valid_url("http://example.com/path?q=1") is True

    def test_localhost_is_valid(self):
        assert ResponseValidator.is_valid_url("http://localhost:8000/api") is True

    def test_ip_address_is_valid(self):
        assert ResponseValidator.is_valid_url("http://192.168.1.1/page") is True

    def test_url_with_port_is_valid(self):
        assert ResponseValidator.is_valid_url("https://api.example.com:443/v1/resource") is True

    def test_no_scheme_is_invalid(self):
        assert ResponseValidator.is_valid_url("example.com") is False

    def test_ftp_scheme_is_invalid(self):
        assert ResponseValidator.is_valid_url("ftp://files.example.com") is False

    def test_empty_string_is_invalid(self):
        assert ResponseValidator.is_valid_url("") is False

    def test_bare_ip_without_scheme_is_invalid(self):
        assert ResponseValidator.is_valid_url("192.168.1.1") is False


# ============================================================================
# Test Class 14: ResponseValidator.is_valid_json
# ============================================================================


class TestResponseValidatorJson:
    """is_valid_json validation."""

    def test_valid_json_object(self):
        assert ResponseValidator.is_valid_json('{"key": "value"}') is True

    def test_valid_json_array(self):
        assert ResponseValidator.is_valid_json("[1, 2, 3]") is True

    def test_valid_json_string(self):
        assert ResponseValidator.is_valid_json('"hello"') is True

    def test_valid_json_number(self):
        assert ResponseValidator.is_valid_json("42") is True

    def test_valid_json_null(self):
        assert ResponseValidator.is_valid_json("null") is True

    def test_valid_json_boolean_true(self):
        assert ResponseValidator.is_valid_json("true") is True

    def test_invalid_json_missing_quotes(self):
        assert ResponseValidator.is_valid_json("{key: value}") is False

    def test_invalid_json_trailing_comma(self):
        assert ResponseValidator.is_valid_json('{"a": 1,}') is False

    def test_invalid_json_empty_string(self):
        assert ResponseValidator.is_valid_json("") is False

    def test_invalid_json_plain_text(self):
        assert ResponseValidator.is_valid_json("not json at all") is False


# ============================================================================
# Test Class 15: ResponseValidator.extract_code_blocks
# ============================================================================


class TestResponseValidatorExtractCodeBlocks:
    """extract_code_blocks parses fenced markdown code blocks."""

    def test_single_python_block(self):
        text = "Some text\n```python\nprint('hello')\n```\nmore text"
        blocks = ResponseValidator.extract_code_blocks(text)
        assert len(blocks) == 1
        lang, code = blocks[0]
        assert lang == "python"
        assert "print('hello')" in code

    def test_block_without_language_defaults_to_text(self):
        text = "```\nhello world\n```"
        blocks = ResponseValidator.extract_code_blocks(text)
        assert len(blocks) == 1
        lang, code = blocks[0]
        assert lang == "text"
        assert code == "hello world"

    def test_multiple_blocks_extracted(self):
        text = "First block:\n```python\nx = 1\n```\nSecond block:\n```bash\nls -la\n```"
        blocks = ResponseValidator.extract_code_blocks(text)
        assert len(blocks) == 2
        langs = {b[0] for b in blocks}
        assert "python" in langs
        assert "bash" in langs

    def test_no_blocks_returns_empty_list(self):
        text = "No code here, just plain text."
        blocks = ResponseValidator.extract_code_blocks(text)
        assert blocks == []

    def test_code_is_stripped_of_leading_trailing_whitespace(self):
        text = "```python\n  x = 42  \n```"
        blocks = ResponseValidator.extract_code_blocks(text)
        _, code = blocks[0]
        assert code == "x = 42"


# ============================================================================
# Test Class 16: Singleton and try_bypass_llm
# ============================================================================


class TestSingletonAndBypass:
    """get_smart_router singleton and try_bypass_llm helper."""

    def test_get_smart_router_returns_smart_router_instance(self):
        router = get_smart_router()
        assert isinstance(router, SmartRouter)

    def test_get_smart_router_returns_same_instance_on_repeated_calls(self):
        router1 = get_smart_router()
        router2 = get_smart_router()
        assert router1 is router2

    def test_singleton_is_none_before_first_call(self):
        # autouse fixture already reset to None; confirm fresh creation
        assert smart_router_module._router is None
        get_smart_router()
        assert smart_router_module._router is not None

    def test_try_bypass_llm_delegates_to_singleton(self):
        result = try_bypass_llm("hello")
        assert isinstance(result, RoutingResult)
        assert result.decision == RouteDecision.DIRECT_RESPONSE

    def test_try_bypass_llm_with_needs_llm_message(self):
        result = try_bypass_llm("Explain Turing completeness in detail please.")
        assert result.decision == RouteDecision.NEEDS_LLM

    def test_try_bypass_llm_with_context_does_not_crash(self):
        result = try_bypass_llm("hi", context={"session_id": "abc123"})
        assert isinstance(result, RoutingResult)

    def test_try_bypass_llm_uses_singleton_not_new_instance(self):
        router_a = get_smart_router()
        try_bypass_llm("hello")
        router_b = get_smart_router()
        # Both calls should have modified the SAME singleton stats
        assert router_a is router_b
        assert router_a.get_stats()["total_routes"] >= 1
