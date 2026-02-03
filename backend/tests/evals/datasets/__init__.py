"""Built-in evaluation datasets.

This module provides pre-built evaluation datasets for common testing scenarios.
Datasets can be loaded directly or used as templates for custom datasets.

Available datasets:
- basic_qa: Basic question-answering tests
- tool_use: Tool calling validation tests
- code_generation: Code generation quality tests
- research: Research task tests
"""

from tests.evals.types import EvalCase, EvalDataset


def get_basic_qa_dataset() -> EvalDataset:
    """Get a basic QA evaluation dataset.

    Tests fundamental response quality including:
    - Greeting responses
    - Simple factual questions
    - Instruction following
    """
    return EvalDataset(
        name="basic_qa",
        description="Basic question-answering evaluation",
        tags=["basic", "qa"],
        cases=[
            EvalCase(
                id="greeting_response",
                name="Greeting Response",
                input="Hello! How are you?",
                expected_output_contains=["hello", "hi", "hey"],
                tags=["greeting"],
            ),
            EvalCase(
                id="simple_math",
                name="Simple Math",
                input="What is 2 + 2?",
                expected_output_contains=["4", "four"],
                tags=["math", "factual"],
            ),
            EvalCase(
                id="instruction_follow",
                name="Instruction Following",
                input="Say the word 'banana' three times.",
                expected_output_contains=["banana"],
                tags=["instructions"],
            ),
            EvalCase(
                id="capital_question",
                name="Capital Question",
                input="What is the capital of France?",
                expected_output_contains=["Paris"],
                tags=["factual", "geography"],
            ),
            EvalCase(
                id="list_request",
                name="List Generation",
                input="List 3 colors.",
                expected_output_contains=["red", "blue", "green", "yellow", "orange", "purple"],
                min_similarity=0.5,
                tags=["list", "instructions"],
            ),
        ],
    )


def get_tool_use_dataset() -> EvalDataset:
    """Get a tool usage evaluation dataset.

    Tests agent's ability to:
    - Select appropriate tools
    - Pass correct arguments
    - Handle tool results
    """
    return EvalDataset(
        name="tool_use",
        description="Tool usage validation",
        tags=["tools", "agent"],
        cases=[
            EvalCase(
                id="file_read",
                name="File Read Tool",
                input="Read the contents of /tmp/test.txt",
                expected_tool_calls=[{"function_name": "file_read", "arguments": {"path": "/tmp/test.txt"}}],
                tags=["file", "tools"],
            ),
            EvalCase(
                id="web_search",
                name="Web Search Tool",
                input="Search the web for 'Python tutorials'",
                expected_tool_calls=[{"function_name": "info_search_web"}],
                tags=["search", "tools"],
            ),
            EvalCase(
                id="shell_command",
                name="Shell Command Tool",
                input="List files in the current directory",
                expected_tool_calls=[{"function_name": "shell_run"}],
                tags=["shell", "tools"],
            ),
            EvalCase(
                id="browser_navigate",
                name="Browser Navigation",
                input="Open google.com in the browser",
                expected_tool_calls=[{"function_name": "browser_view", "arguments": {"url": "google.com"}}],
                tags=["browser", "tools"],
            ),
        ],
    )


def get_code_generation_dataset() -> EvalDataset:
    """Get a code generation evaluation dataset.

    Tests code generation quality including:
    - Syntax correctness
    - Functionality
    - Style
    """
    return EvalDataset(
        name="code_generation",
        description="Code generation quality evaluation",
        tags=["code", "generation"],
        cases=[
            EvalCase(
                id="python_function",
                name="Python Function Generation",
                input="Write a Python function that adds two numbers.",
                expected_output_contains=["def", "return"],
                expected_output_not_contains=["error", "invalid"],
                tags=["python", "function"],
            ),
            EvalCase(
                id="python_class",
                name="Python Class Generation",
                input="Write a Python class called 'Person' with name and age attributes.",
                expected_output_contains=["class Person", "def __init__", "self.name", "self.age"],
                tags=["python", "class"],
            ),
            EvalCase(
                id="javascript_function",
                name="JavaScript Function Generation",
                input="Write a JavaScript function that reverses a string.",
                expected_output_contains=["function", "return"],
                tags=["javascript", "function"],
            ),
            EvalCase(
                id="sql_query",
                name="SQL Query Generation",
                input="Write a SQL query to select all users older than 18.",
                expected_output_contains=["SELECT", "FROM", "WHERE"],
                tags=["sql", "query"],
            ),
        ],
    )


def get_research_dataset() -> EvalDataset:
    """Get a research task evaluation dataset.

    Tests research and analysis capabilities.
    """
    return EvalDataset(
        name="research",
        description="Research and analysis evaluation",
        tags=["research", "analysis"],
        cases=[
            EvalCase(
                id="topic_summary",
                name="Topic Summary",
                input="Summarize the key concepts of machine learning.",
                expected_output_contains=["algorithm", "data", "model", "training", "prediction"],
                min_similarity=0.6,
                tags=["summary", "ml"],
            ),
            EvalCase(
                id="comparison",
                name="Comparison Task",
                input="Compare Python and JavaScript for web development.",
                expected_output_contains=["Python", "JavaScript"],
                tags=["comparison"],
            ),
            EvalCase(
                id="explanation",
                name="Technical Explanation",
                input="Explain how REST APIs work.",
                expected_output_contains=["HTTP", "request", "response", "endpoint"],
                tags=["explanation", "api"],
            ),
        ],
    )


def get_structured_output_dataset() -> EvalDataset:
    """Get a structured output evaluation dataset.

    Tests ability to produce correctly formatted structured outputs.
    """
    return EvalDataset(
        name="structured_output",
        description="Structured output format validation",
        tags=["structured", "json"],
        cases=[
            EvalCase(
                id="json_object",
                name="JSON Object Output",
                input="Return a JSON object with name='John' and age=30.",
                expected_json_schema={
                    "type": "object",
                    "required": ["name", "age"],
                    "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
                },
                tags=["json", "object"],
            ),
            EvalCase(
                id="json_array",
                name="JSON Array Output",
                input="Return a JSON array with three fruits.",
                expected_json_schema={"type": "array", "minItems": 3, "items": {"type": "string"}},
                tags=["json", "array"],
            ),
        ],
    )


# Registry of all built-in datasets
BUILTIN_DATASETS = {
    "basic_qa": get_basic_qa_dataset,
    "tool_use": get_tool_use_dataset,
    "code_generation": get_code_generation_dataset,
    "research": get_research_dataset,
    "structured_output": get_structured_output_dataset,
}


def get_dataset(name: str) -> EvalDataset:
    """Get a built-in dataset by name.

    Args:
        name: Dataset name

    Returns:
        EvalDataset instance

    Raises:
        KeyError: If dataset not found
    """
    if name not in BUILTIN_DATASETS:
        available = ", ".join(BUILTIN_DATASETS.keys())
        raise KeyError(f"Dataset '{name}' not found. Available: {available}")

    return BUILTIN_DATASETS[name]()


def list_datasets() -> list[str]:
    """List all available built-in datasets."""
    return list(BUILTIN_DATASETS.keys())
