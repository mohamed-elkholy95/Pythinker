"""
Shell Service Implementation - Async Version
"""

import os
import uuid
import getpass
import socket
import logging
import asyncio
import re
from typing import Any, Dict, List, Optional
from app.models.shell import (
    ShellExecResult,
    ShellViewResult,
    ShellWaitResult,
    ShellWriteResult,
    ShellKillResult,
    ShellTask,
    ConsoleRecord,
)
from app.core.exceptions import (
    AppException,
    ResourceNotFoundException,
    BadRequestException,
)
from app.core.config import settings

# Set up logger
logger = logging.getLogger(__name__)

CMD_BEGIN_MARKER = "[CMD_BEGIN]"
CMD_END_MARKER = "[CMD_END]"


class ShellService:
    # Store active shell sessions
    active_shells: Dict[str, Dict[str, Any]] = {}

    # Store shell tasks
    shell_tasks: Dict[str, ShellTask] = {}
    _HOME_ALIAS_FROM = "/home/user"
    _HOME_ALIAS_TO = "/home/ubuntu"

    def _resolve_home_alias(self, path: str) -> str:
        """Translate legacy /home/user paths to the sandbox user home."""
        if path == self._HOME_ALIAS_FROM:
            return self._HOME_ALIAS_TO
        if path.startswith(f"{self._HOME_ALIAS_FROM}/"):
            suffix = path[len(self._HOME_ALIAS_FROM) + 1 :]
            return f"{self._HOME_ALIAS_TO}/{suffix}"
        return path

    def _remove_ansi_escape_codes(self, text: str) -> str:
        """Remove ANSI escape codes from text"""
        # Pattern to match ANSI escape sequences
        ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        return ansi_escape.sub("", text)

    def _get_display_path(self, path: str) -> str:
        """Get the path for display, replacing user home directory with ~"""
        home_dir = os.path.expanduser("~")
        logger.debug(f"Home directory: {home_dir} , path: {path}")
        if path.startswith(home_dir):
            return path.replace(home_dir, "~", 1)
        return path

    def _format_ps1(self, exec_dir: str) -> str:
        """Format the command prompt, optionally with structured markers."""
        username = getpass.getuser()
        hostname = socket.gethostname()
        display_path = self._get_display_path(exec_dir)

        if settings.SHELL_USE_STRUCTURED_MARKERS:
            return f"\n{username}@{hostname}:{display_path}\n{CMD_END_MARKER}"

        return f"{username}@{hostname}:{display_path} $"

    def _append_output(self, shell: Dict[str, Any], output: str) -> None:
        """Append output while enforcing a max buffer size."""
        if not output:
            return

        max_chars = settings.SHELL_MAX_OUTPUT_CHARS
        shell["output"] = (shell["output"] + output)[-max_chars:]

        if shell.get("console"):
            shell["console"][-1].output = (shell["console"][-1].output + output)[
                -max_chars:
            ]

    async def _create_process(
        self, command: str, exec_dir: str
    ) -> asyncio.subprocess.Process:
        """Create a new async subprocess"""
        logger.debug(
            f"Creating process for command: {command} in directory: {exec_dir}"
        )
        return await asyncio.create_subprocess_shell(
            command,
            executable="/bin/bash",
            cwd=exec_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,  # Redirect stderr to stdout
            stdin=asyncio.subprocess.PIPE,
            limit=1024 * 1024,  # Set buffer size to 1MB
        )

    async def _start_output_reader(
        self, session_id: str, process: asyncio.subprocess.Process
    ):
        """Start a coroutine to continuously read process output and store it"""
        logger.debug(f"Starting output reader for session: {session_id}")
        while True:
            if process.stdout:
                try:
                    buffer = await process.stdout.read(128)
                    if not buffer:
                        # Process output ended
                        break

                    output = buffer.decode("utf-8")
                    # Add output to shell session
                    shell = self.active_shells.get(session_id)
                    if shell:
                        self._append_output(shell, output)
                except Exception as e:
                    logger.error(
                        f"Error reading process output: {str(e)}", exc_info=True
                    )
                    break
            else:
                break

        logger.debug(f"Output reader for session {session_id} has finished")

    async def exec_command(
        self, session_id: str, exec_dir: Optional[str], command: str
    ) -> ShellExecResult:
        """
        Asynchronously execute a command in the specified shell session
        """
        logger.info(f"Executing command in session {session_id}: {command}")

        # Enforce ALLOW_SUDO — reject sudo commands when disabled
        if not settings.ALLOW_SUDO:
            stripped = command.strip()
            if stripped == "sudo" or stripped.startswith("sudo "):
                logger.warning(f"Rejected sudo command (ALLOW_SUDO=false): {command}")
                raise BadRequestException(
                    "sudo commands are disabled in this sandbox (ALLOW_SUDO=false)"
                )

        if not exec_dir:
            exec_dir = os.path.expanduser("~")
        exec_dir = self._resolve_home_alias(exec_dir)
        if not os.path.isabs(exec_dir):
            exec_dir = os.path.abspath(exec_dir)

        # Ensure directory exists
        if not os.path.exists(exec_dir):
            if exec_dir == "/workspace" or exec_dir.startswith("/workspace/"):
                try:
                    os.makedirs(exec_dir, exist_ok=True)
                    logger.info(f"Created missing workspace directory: {exec_dir}")
                except OSError as e:
                    logger.error(
                        f"Failed to create workspace directory {exec_dir}: {e}"
                    )
                    raise BadRequestException(
                        f"Directory does not exist: {exec_dir}"
                    ) from e
            else:
                logger.error(f"Directory does not exist: {exec_dir}")
                raise BadRequestException(f"Directory does not exist: {exec_dir}")

        try:
            # Create PS1 format
            ps1 = self._format_ps1(exec_dir)

            # Build the output header (PS1 + command echo)
            if settings.SHELL_USE_STRUCTURED_MARKERS:
                header = f"{CMD_BEGIN_MARKER}{ps1} {command}\n"
            else:
                header = f"{ps1} {command}\n"

            # If it's a new session, create a new process
            if session_id not in self.active_shells:
                logger.debug(f"Creating new shell session: {session_id}")
                process = await self._create_process(command, exec_dir)
                self.active_shells[session_id] = {
                    "process": process,
                    "exec_dir": exec_dir,
                    "output": header,
                    "console": [ConsoleRecord(ps1=ps1, command=command, output=header)],
                }
                # Start the output reader coroutine
                asyncio.create_task(self._start_output_reader(session_id, process))
            else:
                # Execute command in an existing session
                logger.debug(f"Using existing shell session: {session_id}")
                shell = self.active_shells[session_id]
                old_process = shell["process"]

                # If the old process is still running, terminate it first
                if old_process.returncode is None:
                    logger.debug(
                        f"Terminating previous process in session: {session_id}"
                    )
                    try:
                        old_process.terminate()
                        await asyncio.wait_for(old_process.wait(), timeout=1)
                    except (asyncio.TimeoutError, ProcessLookupError, OSError) as e:
                        # If graceful termination fails, force kill
                        logger.warning(
                            f"Forcefully killing process in session {session_id}: {e}"
                        )
                        old_process.kill()

                # Create a new process
                process = await self._create_process(command, exec_dir)

                # Update session information
                self.active_shells[session_id]["process"] = process
                self.active_shells[session_id]["exec_dir"] = exec_dir
                self.active_shells[session_id]["output"] = header  # Start with header

                # Record command console record with header
                shell["console"].append(
                    ConsoleRecord(ps1=ps1, command=command, output=header)
                )

                # Start the output reader coroutine
                asyncio.create_task(self._start_output_reader(session_id, process))

            # Try to wait for the process to complete (max 5 seconds)
            try:
                logger.debug(f"Waiting for process completion in session: {session_id}")
                wait_result = await self.wait_for_process(session_id, seconds=5)
                if wait_result.returncode is not None:
                    # Process has completed — give the output reader task a
                    # moment to drain any remaining buffered stdout before we
                    # read the accumulated output.
                    logger.debug(
                        f"Process completed with code: {wait_result.returncode}"
                    )
                    await asyncio.sleep(0.1)

                    # Explicitly drain any bytes still sitting in the pipe
                    shell = self.active_shells.get(session_id)
                    if shell:
                        process = shell["process"]
                        if process.stdout:
                            try:
                                remaining = await asyncio.wait_for(
                                    process.stdout.read(), timeout=1.0
                                )
                                if remaining:
                                    self._append_output(
                                        shell,
                                        remaining.decode("utf-8", errors="replace"),
                                    )
                            except (asyncio.TimeoutError, Exception):
                                pass

                        # Record exit code on the console record
                        if shell.get("console") and process.returncode is not None:
                            shell["console"][-1].exit_code = process.returncode

                    view_result = await self.view_shell(session_id)

                    return ShellExecResult(
                        session_id=session_id,
                        command=command,
                        status="completed",
                        returncode=wait_result.returncode,
                        output=view_result.output,
                    )
            except BadRequestException:
                # Wait timeout, process still running
                logger.debug(
                    f"Process still running after timeout in session: {session_id}"
                )
                pass
            except Exception as e:
                # Other exceptions, ignore and continue
                logger.warning(f"Exception while waiting for process: {str(e)}")
                pass

            return ShellExecResult(
                session_id=session_id,
                command=command,
                status="running",
            )
        except Exception as e:
            logger.error(f"Command execution failed: {str(e)}", exc_info=True)
            raise AppException(
                message=f"Command execution failed: {str(e)}",
                data={"session_id": session_id, "command": command},
            )

    async def view_shell(
        self, session_id: str, console: bool = False
    ) -> ShellViewResult:
        """
        Asynchronously view the content of the specified shell session
        """
        logger.debug(f"Viewing shell content for session: {session_id}")
        if session_id not in self.active_shells:
            logger.info(f"Session ID not found: {session_id}")
            raise ResourceNotFoundException(f"Session ID does not exist: {session_id}")

        shell = self.active_shells[session_id]

        # Get raw output and filter ANSI escape codes
        raw_output = shell["output"]
        clean_output = self._remove_ansi_escape_codes(raw_output)

        # Get command console records with filtered output
        if console:
            console = self.get_console_records(session_id)
        else:
            console = None

        return ShellViewResult(
            output=clean_output, session_id=session_id, console=console
        )

    def get_console_records(self, session_id: str) -> List[ConsoleRecord]:
        """
        Get command console records for the specified session (this method doesn't need to be async)
        """
        logger.debug(f"Getting console records for session: {session_id}")
        if session_id not in self.active_shells:
            logger.info(f"Session ID not found: {session_id}")
            raise ResourceNotFoundException(f"Session ID does not exist: {session_id}")

        # Get raw console records and filter ANSI escape codes
        raw_console = self.active_shells[session_id]["console"]
        clean_console = []
        for record in raw_console:
            clean_record = ConsoleRecord(
                ps1=record.ps1,
                command=record.command,
                output=self._remove_ansi_escape_codes(record.output),
                exit_code=record.exit_code,
            )
            clean_console.append(clean_record)

        return clean_console

    async def wait_for_process(
        self, session_id: str, seconds: Optional[int] = None
    ) -> ShellWaitResult:
        """
        Asynchronously wait for the process in the specified shell session to return
        """
        logger.debug(
            f"Waiting for process in session: {session_id}, timeout: {seconds}s"
        )
        if session_id not in self.active_shells:
            logger.info(f"Session ID not found: {session_id}")
            raise ResourceNotFoundException(f"Session ID does not exist: {session_id}")

        shell = self.active_shells[session_id]
        process = shell["process"]

        try:
            # Asynchronously wait for process to complete
            if seconds is None:
                seconds = 60
            await asyncio.wait_for(process.wait(), timeout=seconds)

            logger.info(f"Process completed with return code: {process.returncode}")
            return ShellWaitResult(returncode=process.returncode)
        except asyncio.TimeoutError:
            logger.warning(f"Process wait timeout expired: {seconds}s")
            raise BadRequestException(f"Wait timeout: {seconds} seconds")
        except Exception as e:
            logger.error(f"Failed to wait for process: {str(e)}", exc_info=True)
            raise AppException(message=f"Failed to wait for process: {str(e)}")

    async def write_to_process(
        self, session_id: str, input_text: str, press_enter: bool
    ) -> ShellWriteResult:
        """
        Asynchronously write input to the process in the specified shell session
        """
        logger.debug(
            f"Writing to process in session: {session_id}, press_enter: {press_enter}"
        )
        if session_id not in self.active_shells:
            logger.info(f"Session ID not found: {session_id}")
            raise ResourceNotFoundException(f"Session ID does not exist: {session_id}")

        shell = self.active_shells[session_id]
        process = shell["process"]

        try:
            # Check if the process is still running
            if process.returncode is not None:
                logger.error("Process has already terminated, cannot write input")
                raise BadRequestException("Process has ended, cannot write input")

            # Prepare input data
            if press_enter:
                input_data = f"{input_text}\n".encode()
            else:
                input_data = input_text.encode()

            # Add input to output and console records
            input_str = input_data.decode("utf-8")
            self._append_output(shell, input_str)

            # Asynchronously write input
            process.stdin.write(input_data)
            await process.stdin.drain()

            logger.info("Successfully wrote input to process")

            return ShellWriteResult(status="success")
        except Exception as e:
            logger.error(f"Failed to write input: {str(e)}", exc_info=True)
            raise AppException(message=f"Failed to write input: {str(e)}")

    async def kill_process(self, session_id: str) -> ShellKillResult:
        """
        Asynchronously terminate the process in the specified shell session
        """
        logger.info(f"Killing process in session: {session_id}")
        if session_id not in self.active_shells:
            logger.info(f"Session ID not found: {session_id}")
            raise ResourceNotFoundException(f"Session ID does not exist: {session_id}")

        shell = self.active_shells[session_id]
        process = shell["process"]

        try:
            # Check if the process is still running
            if process.returncode is None:
                # Try to terminate gracefully
                logger.debug("Attempting to terminate process gracefully")
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=3)
                except asyncio.TimeoutError:
                    # If graceful termination fails, force kill
                    logger.warning("Forcefully killing the process")
                    process.kill()
                    await process.wait()

                logger.info(
                    f"Process terminated with return code: {process.returncode}"
                )
                return ShellKillResult(
                    status="terminated", returncode=process.returncode
                )
            else:
                logger.info(
                    f"Process was already terminated with return code: {process.returncode}"
                )
                return ShellKillResult(
                    status="already_terminated", returncode=process.returncode
                )
        except Exception as e:
            logger.error(f"Failed to kill process: {str(e)}", exc_info=True)
            raise AppException(message=f"Failed to terminate process: {str(e)}")

    def create_session_id(self) -> str:
        """
        Create a new session ID (this method doesn't need to be async)
        """
        session_id = str(uuid.uuid4())
        logger.debug(f"Created new session ID: {session_id}")
        return session_id


shell_service = ShellService()
