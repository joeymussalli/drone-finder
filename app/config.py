"""Configuration loader for Drone Finder."""

import os
from dotenv import load_dotenv
from app.models import AppConfig, SearchArea


class ConfigError(Exception):
    """Raised when a required configuration key is missing."""
    def __init__(self, key: str) -> None:
        super().__init__(f"Missing required config key: {key}")
        self.key = key


def load_config() -> AppConfig:
    """Load and validate all configuration from .env, return AppConfig."""
    load_dotenv()

    def require(key: str) -> str:
        val = os.environ.get(key)
        if val is None:
            raise ConfigError(key)
        return val

    mode = require("MODE")
    width_m = float(require("SEARCH_AREA_WIDTH_M"))
    depth_m = float(require("SEARCH_AREA_DEPTH_M"))
    sim_images_dir = require("SIM_IMAGES_DIR")
    sim_target_raw = require("SIM_TARGET_CELL")
    col_str, row_str = sim_target_raw.split(",")
    sim_target_cell = (int(col_str.strip()), int(row_str.strip()))
    anthropic_api_key = require("ANTHROPIC_API_KEY")
    llm_provider = require("LLM_PROVIDER")
    esp32_address = require("ESP32_ADDRESS")
    voice_input_enabled = require("VOICE_INPUT_ENABLED").strip().lower() == "true"
    step_size_m = float(require("STEP_SIZE_M"))
    # Optional: total target duration (seconds) for the full demo sweep.
    # Defaults to 35s when unset so existing .env files keep working.
    demo_speed_s = float(os.environ.get("DEMO_SPEED_S", "35"))
    # Optional: ESP32-CAM MJPEG stream, used in "camera" and "real" modes.
    camera_url = os.environ.get("CAMERA_URL", "http://192.168.4.1:81/stream").strip()

    return AppConfig(
        mode=mode,
        search_area=SearchArea(width_m=width_m, depth_m=depth_m),
        sim_images_dir=sim_images_dir,
        sim_target_cell=sim_target_cell,
        anthropic_api_key=anthropic_api_key,
        llm_provider=llm_provider,
        esp32_address=esp32_address,
        voice_input_enabled=voice_input_enabled,
        step_size_m=step_size_m,
        demo_speed_s=demo_speed_s,
        camera_url=camera_url,
    )
