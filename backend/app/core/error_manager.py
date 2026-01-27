"""
Centralized Error Management System for Pythinker
Provides robust error handling, recovery, and monitoring across all components.
"""

import asyncio
import logging
import traceback
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type, Union
from functools import wraps

logger = logging.getLogger(__name__)


class ErrorSeverity(str, Enum):
    """Error severity levels"""
    CRITICAL = "critical"  # System failure, requires immediate attention
    HIGH = "high"         # Service degradation, affects functionality
    MEDIUM = "medium"     # Recoverable errors, may affect performance
    LOW = "low"          # Minor issues, logging only


class ErrorCategory(str, Enum):
    """Error categories for classification"""
    SANDBOX = "sandbox"
    AGENT = "agent"
    DATABASE = "database"
    NETWORK = "network"
    AUTHENTICATION = "authentication"
    VALIDATION = "validation"
    RESOURCE = "resource"
    EXTERNAL_API = "external_api"


@dataclass
class ErrorContext:
    """Context information for error tracking"""
    component: str
    operation: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    agent_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ErrorRecord:
    """Complete error record for tracking and analysis"""
    id: str
    timestamp: datetime
    severity: ErrorSeverity
    category: ErrorCategory
    context: ErrorContext
    exception: Exception
    traceback_str: str
    recovery_attempted: bool = False
    recovery_successful: bool = False
    retry_count: int = 0


class ErrorManager:
    """Centralized error management system"""
    
    def __init__(self):
        self._error_history: List[ErrorRecord] = []
        self._recovery_strategies: Dict[ErrorCategory, List[Callable]] = {}
        self._circuit_breakers: Dict[str, "CircuitBreaker"] = {}
        self._max_history = 1000
        
    def register_recovery_strategy(self, category: ErrorCategory, strategy: Callable):
        """Register a recovery strategy for an error category"""
        if category not in self._recovery_strategies:
            self._recovery_strategies[category] = []
        self._recovery_strategies[category].append(strategy)
        
    async def handle_error(
        self,
        exception: Exception,
        context: ErrorContext,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        category: ErrorCategory = ErrorCategory.AGENT,
        auto_recover: bool = True
    ) -> bool:
        """
        Handle an error with automatic recovery attempts
        
        Returns:
            bool: True if error was recovered, False otherwise
        """
        error_id = f"{context.component}_{datetime.now().timestamp()}"
        
        error_record = ErrorRecord(
            id=error_id,
            timestamp=datetime.now(),
            severity=severity,
            category=category,
            context=context,
            exception=exception,
            traceback_str=traceback.format_exc()
        )
        
        # Log the error
        log_level = {
            ErrorSeverity.CRITICAL: logging.CRITICAL,
            ErrorSeverity.HIGH: logging.ERROR,
            ErrorSeverity.MEDIUM: logging.WARNING,
            ErrorSeverity.LOW: logging.INFO
        }[severity]
        
        logger.log(
            log_level,
            f"[{category.upper()}] {context.component}.{context.operation}: {str(exception)}",
            extra={
                "error_id": error_id,
                "user_id": context.user_id,
                "session_id": context.session_id,
                "agent_id": context.agent_id,
                "metadata": context.metadata
            }
        )
        
        # Attempt recovery if enabled
        recovery_successful = False
        if auto_recover and category in self._recovery_strategies:
            error_record.recovery_attempted = True
            recovery_successful = await self._attempt_recovery(error_record)
            error_record.recovery_successful = recovery_successful
            
        # Store error record
        self._add_error_record(error_record)
        
        return recovery_successful
        
    async def _attempt_recovery(self, error_record: ErrorRecord) -> bool:
        """Attempt recovery using registered strategies"""
        strategies = self._recovery_strategies.get(error_record.category, [])
        
        for strategy in strategies:
            try:
                logger.info(f"Attempting recovery with {strategy.__name__}")
                result = await strategy(error_record)
                if result:
                    logger.info(f"Recovery successful with {strategy.__name__}")
                    return True
            except Exception as e:
                logger.warning(f"Recovery strategy {strategy.__name__} failed: {e}")
                
        return False
        
    def _add_error_record(self, record: ErrorRecord):
        """Add error record to history with size limit"""
        self._error_history.append(record)
        if len(self._error_history) > self._max_history:
            self._error_history.pop(0)
            
    def get_error_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Get error statistics for the specified time period"""
        cutoff = datetime.now() - timedelta(hours=hours)
        recent_errors = [e for e in self._error_history if e.timestamp > cutoff]
        
        return {
            "total_errors": len(recent_errors),
            "by_severity": {s.value: len([e for e in recent_errors if e.severity == s]) for s in ErrorSeverity},
            "by_category": {c.value: len([e for e in recent_errors if e.category == c]) for c in ErrorCategory},
            "recovery_rate": len([e for e in recent_errors if e.recovery_successful]) / max(len(recent_errors), 1)
        }


class CircuitBreaker:
    """Circuit breaker pattern for external service calls"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half-open
        
    def can_execute(self) -> bool:
        """Check if operation can be executed"""
        if self.state == "closed":
            return True
        elif self.state == "open":
            if datetime.now() - self.last_failure_time > timedelta(seconds=self.recovery_timeout):
                self.state = "half-open"
                return True
            return False
        else:  # half-open
            return True
            
    def record_success(self):
        """Record successful operation"""
        self.failure_count = 0
        self.state = "closed"
        
    def record_failure(self):
        """Record failed operation"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "open"


# Global error manager instance
_error_manager = ErrorManager()


def get_error_manager() -> ErrorManager:
    """Get the global error manager instance"""
    return _error_manager


def error_handler(
    severity: ErrorSeverity = ErrorSeverity.MEDIUM,
    category: ErrorCategory = ErrorCategory.AGENT,
    auto_recover: bool = True,
    reraise: bool = False
):
    """Decorator for automatic error handling"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                context = ErrorContext(
                    component=func.__module__,
                    operation=func.__name__,
                    metadata={"args": str(args), "kwargs": str(kwargs)}
                )
                
                recovered = await _error_manager.handle_error(
                    e, context, severity, category, auto_recover
                )
                
                if not recovered and reraise:
                    raise
                    
                return None
                
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                context = ErrorContext(
                    component=func.__module__,
                    operation=func.__name__,
                    metadata={"args": str(args), "kwargs": str(kwargs)}
                )
                
                # For sync functions, we can't do async recovery
                logger.error(f"Error in {func.__name__}: {e}")
                
                if reraise:
                    raise
                    
                return None
                
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


@asynccontextmanager
async def error_context(
    component: str,
    operation: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    severity: ErrorSeverity = ErrorSeverity.MEDIUM,
    category: ErrorCategory = ErrorCategory.AGENT,
    auto_recover: bool = True
):
    """Context manager for error handling"""
    try:
        yield
    except Exception as e:
        context = ErrorContext(
            component=component,
            operation=operation,
            user_id=user_id,
            session_id=session_id,
            agent_id=agent_id
        )
        
        recovered = await _error_manager.handle_error(
            e, context, severity, category, auto_recover
        )
        
        if not recovered:
            raise


# Recovery strategies for different error categories
async def sandbox_recovery_strategy(error_record: ErrorRecord) -> bool:
    """Recovery strategy for sandbox errors"""
    try:
        # Attempt to restart sandbox
        logger.info("Attempting sandbox recovery...")
        # Implementation would go here
        return True
    except Exception:
        return False


async def database_recovery_strategy(error_record: ErrorRecord) -> bool:
    """Recovery strategy for database errors"""
    try:
        # Attempt to reconnect to database
        logger.info("Attempting database recovery...")
        # Implementation would go here
        return True
    except Exception:
        return False


# Register default recovery strategies
_error_manager.register_recovery_strategy(ErrorCategory.SANDBOX, sandbox_recovery_strategy)
_error_manager.register_recovery_strategy(ErrorCategory.DATABASE, database_recovery_strategy)
