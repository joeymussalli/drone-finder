"""Abstract interface for drone flight commands."""

from abc import ABC, abstractmethod
from app.models import Direction


class DroneCommandError(Exception):
    """Raised when a drone command fails or times out."""
    pass


class DroneInterface(ABC):
    """Abstract base class for all drone adapters (sim and real).
    
    All methods are async. Callers issue commands through this interface
    only — concrete adapter details are hidden from all other components.
    """

    @abstractmethod
    async def takeoff(self) -> None:
        """Command the drone to take off."""
        ...

    @abstractmethod
    async def land(self) -> None:
        """Command the drone to land in place."""
        ...

    @abstractmethod
    async def move(self, direction: Direction, distance_m: float) -> None:
        """Move in the given direction by distance_m metres.
        
        direction: one of Direction.FORWARD/BACKWARD/LEFT/RIGHT
        distance_m: 0.1 to 500.0
        """
        ...

    @abstractmethod
    async def turn(self, angle_deg: float) -> None:
        """Rotate by angle_deg degrees. Negative = left, positive = right.
        
        angle_deg: -360 to 360
        """
        ...

    @abstractmethod
    async def hover(self, duration_s: float) -> None:
        """Hold position for duration_s seconds.
        
        duration_s: 0.1 to 300.0
        """
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Immediately stop all movement."""
        ...
