"""
Supervisor business model definitions
"""

from pydantic import BaseModel, Field


class ProcessInfo(BaseModel):
    """Process information model"""

    name: str = Field(..., description="Process name")
    group: str = Field(..., description="Process group")
    description: str = Field(..., description="Process description")
    start: int = Field(..., description="Start timestamp")
    stop: int = Field(..., description="Stop timestamp")
    now: int = Field(..., description="Current timestamp")
    state: int = Field(..., description="State code")
    statename: str = Field(..., description="State name")
    spawnerr: str = Field(..., description="Spawn error")
    exitstatus: int = Field(..., description="Exit status code")
    logfile: str = Field(..., description="Log file")
    stdout_logfile: str = Field(..., description="Standard output log file")
    stderr_logfile: str = Field(..., description="Standard error log file")
    pid: int = Field(..., description="Process ID")


class SupervisorActionResult(BaseModel):
    """Supervisor operation result model"""

    status: str = Field(..., description="Operation status")
    result: list[str] | None = Field(None, description="Operation result")
    stop_result: list[str] | None = Field(None, description="Stop result")
    start_result: list[str] | None = Field(None, description="Start result")
    shutdown_result: list[str] | None = Field(None, description="Shutdown result")


class SupervisorTimeout(BaseModel):
    """Supervisor timeout model"""

    status: str | None = Field(None, description="Timeout setting status")
    active: bool = Field(False, description="Whether timeout is active")
    shutdown_time: str | None = Field(None, description="Shutdown time")
    timeout_minutes: float | None = Field(None, description="Timeout duration (minutes)")
    remaining_seconds: float | None = Field(None, description="Remaining seconds")
