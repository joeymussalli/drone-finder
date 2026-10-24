"""Simulation video source -- serves JPEG frames from disk by grid cell."""

from pathlib import Path


# File extensions treated as simulation photos.
_IMAGE_EXTS = (".jpg", ".jpeg", ".png")
# The target photo filename (stem match, case-insensitive).
_TARGET_STEM = "target"


class SimVideoSource:
    """Serves still photos as a fake video stream for simulation mode.

    Drop any photos into the sim images directory:
      - One photo whose filename (without extension) is ``target`` -- e.g.
        ``target.jpg`` -- is the photo that CONTAINS the item to be found.
      - Every OTHER image file (any name) is treated as a non-target room
        photo and served when the drone is not on the target cell.

    When the simulated drone is on the configured target cell, the target
    photo is served; otherwise the non-target photos are served round-robin.
    This lets a real open-vocabulary detector (YOLO-World) actually find the
    item in the target photo during the demo.
    """

    def __init__(self, sim_images_dir: str, target_cell: tuple[int, int]) -> None:
        """Load all photos from *sim_images_dir* at construction time.

        Args:
            sim_images_dir: Directory containing ``target.jpg`` plus any number
                of other room photos (any filename).
            target_cell: ``(col, row)`` grid cell where the target item appears.

        Raises:
            FileNotFoundError: If no ``target.*`` photo is found, or if there are
                no non-target photos to serve for the rest of the sweep.
        """
        self._target_cell = target_cell
        self._empty_index = 0

        images_path = Path(sim_images_dir)
        if not images_path.is_dir():
            raise FileNotFoundError(f"Sim images directory not found: {sim_images_dir}")

        target_bytes = None
        non_target: list[bytes] = []

        for path in sorted(images_path.iterdir()):
            if not path.is_file() or path.suffix.lower() not in _IMAGE_EXTS:
                continue
            data = path.read_bytes()
            if path.stem.lower() == _TARGET_STEM:
                target_bytes = data
            else:
                non_target.append(data)

        if target_bytes is None:
            raise FileNotFoundError(
                f"No target photo found in {sim_images_dir}. "
                f"Add a file named 'target.jpg' that contains the item to find."
            )
        if not non_target:
            raise FileNotFoundError(
                f"No non-target room photos found in {sim_images_dir}. "
                f"Add at least one other .jpg (any name) alongside target.jpg."
            )

        self._target_bytes = target_bytes
        self._empty_images = non_target

    def get_frame(self, cell: tuple[int, int]) -> bytes:
        """Return JPEG bytes for the given grid cell position.

        Serves the target photo on the target cell; otherwise round-robins
        through the non-target room photos.
        """
        if cell == self._target_cell:
            return self._target_bytes
        frame = self._empty_images[self._empty_index % len(self._empty_images)]
        self._empty_index += 1
        return frame

    @property
    def target_cell(self) -> tuple[int, int]:
        """The configured target grid cell ``(col, row)``."""
        return self._target_cell
