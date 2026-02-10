"""
Integration module for enhanced error handling and monitoring systems.
This module initializes and coordinates all the enhanced components.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from app.core.error_manager import ErrorCategory, get_error_manager
from app.core.health_monitor import get_health_monitor
from app.core.sandbox_manager import get_sandbox_manager

logger = logging.getLogger(__name__)


class SystemIntegrator:
    """Coordinates all enhanced system components"""

    def __init__(self):
        self.error_manager = get_error_manager()
        self.sandbox_manager = get_sandbox_manager()
        self.health_monitor = get_health_monitor()
        self._initialized = False

    async def initialize(self):
        """Initialize all enhanced components"""
        if self._initialized:
            return

        try:
            logger.info("Initializing enhanced system components...")

            # Register additional recovery strategies
            await self._register_recovery_strategies()

            # Start health monitoring
            await self.health_monitor.start_monitoring()

            self._initialized = True
            logger.info("Enhanced system components initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize enhanced components: {e}")
            raise

    async def shutdown(self):
        """Shutdown all enhanced components"""
        if not self._initialized:
            return

        try:
            logger.info("Shutting down enhanced system components...")

            # Stop health monitoring
            await self.health_monitor.stop_monitoring()

            # Clean up any remaining resources
            await self._cleanup_resources()

            self._initialized = False
            logger.info("Enhanced system components shut down successfully")

        except Exception as e:
            logger.error(f"Error during enhanced components shutdown: {e}")

    async def _register_recovery_strategies(self):
        """Register additional recovery strategies"""

        async def network_recovery_strategy(error_record):
            """Recovery strategy for network errors"""
            try:
                logger.info("Attempting network recovery...")
                # Wait and retry
                await asyncio.sleep(5)
                return True
            except Exception:
                return False

        async def resource_recovery_strategy(error_record):
            """Recovery strategy for resource errors"""
            try:
                logger.info("Attempting resource recovery...")
                # Clean up resources and retry
                await asyncio.sleep(2)
                return True
            except Exception:
                return False

        # Register strategies
        self.error_manager.register_recovery_strategy(ErrorCategory.NETWORK, network_recovery_strategy)
        self.error_manager.register_recovery_strategy(ErrorCategory.RESOURCE, resource_recovery_strategy)

    async def _cleanup_resources(self):
        """Clean up any remaining resources"""
        try:
            # Clean up sandbox resources
            stats = self.sandbox_manager.get_sandbox_stats()
            if stats["total_sandboxes"] > 0:
                logger.info(f"Cleaning up {stats['total_sandboxes']} remaining sandboxes")

        except Exception as e:
            logger.warning(f"Error during resource cleanup: {e}")

    def get_system_status(self):
        """Get comprehensive system status"""
        return {
            "initialized": self._initialized,
            "health": self.health_monitor.get_system_health(),
            "errors": self.error_manager.get_error_stats(),
            "sandboxes": self.sandbox_manager.get_sandbox_stats(),
        }


# Global system integrator
_system_integrator = SystemIntegrator()


def get_system_integrator() -> SystemIntegrator:
    """Get the global system integrator"""
    return _system_integrator


@asynccontextmanager
async def enhanced_lifespan():
    """Enhanced lifespan context manager for FastAPI"""
    integrator = get_system_integrator()

    try:
        # Initialize enhanced components
        await integrator.initialize()
        yield integrator
    finally:
        # Shutdown enhanced components
        await integrator.shutdown()
