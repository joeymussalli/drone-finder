"""Simulation video source — serves JPEG frames from disk by grid cell."""

import os
from pathlib import Path


class SimVideoSource:
    """Serves still JPEG images as a fake video stream for simulation mode.

    Returns the target image when the simulated drone is on the target cell,
    and cycles through empty images for all other cells.

    Satisfies Requirements 11.4, 11.5, 11.6, 11.7:
    - Maintains at least one target image and at least one empty image (11.4).
    - Serves an empty image when the drone is NOT on the target cell (11.5).
    - Serves the target image when the drone IS on the target cell (11.6).
    - Image update is synchronous, so it happens within 500 ms of a cell
      change (11.7).
    """

    def __init__(self, sim_images_dir: str, target_cell: tuple[int, int]) -> None:
        """Load all simulation images from *sim_images_dir* at construction time.

        Args:
            sim_images_dir: Path to the directory that contains ``target.jpg``
                and one or more ``empty_*.jpg`` files.
            target_cell: ``(col, row)`` grid cell where the target item is
                located, as configured by ``SIM_TARGET_CELL``.

        Raises:
            FileNotFoundError: If ``target.jpg`` or no ``empty_*.jpg`` files
                are found in *sim_images_dir*.
        """
        self._target_cell = target_cell
        self._empty_index = 0

        images_path = Path(sim_images_dir)

        # Load target image
        target_path = images_path / "target.jpg"
        if not target_path.exists():
            raise FileNotFoundError(f"target.jpg not found in {sim_images_dir}")
        self._target_bytes = target_path.read_bytes()

        # Load empty images (empty_1.jpg, empty_2.jpg, ...)
        self._empty_images: list[bytes] = []
        for fname in sorted(images_path.glob("empty_*.jpg")):
            self._empty_images.append(fname.read_bytes())

        if not self._empty_images:
            raise FileNotFoundError(f"No empty_*.jpg images found in {sim_images_dir}")

    def get_frame(self, cell: tuple[int, int]) -> bytes:
        """Return JPEG bytes for the given grid cell position.

        Args:
            cell: ``(col, row)`` of the drone's current grid position.

        Returns:
            JPEG bytes of ``target.jpg`` when *cell* matches the configured
            target cell; otherwise JPEG bytes of the next empty image in the
            round-robin sequence.
        """
        if cell == self._target_cell:
            return self._target_bytes
        # Round-robin through empty images
        frame = self._empty_images[self._empty_index % len(self._empty_images)]
        self._empty_index += 1
        return frame

    @property
    def target_cell(self) -> tuple[int, int]:
        """The configured target grid cell ``(col, row)``."""
        return self._target_cell
