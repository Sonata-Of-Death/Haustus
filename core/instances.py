"""Shared singleton instances."""
from core.config import ConfigManager
from core.media import MediaMaestro
from core.resilience import AdaptiveNetworkManager

config_mgr = ConfigManager()
media_maestro = MediaMaestro()
network_mgr = AdaptiveNetworkManager()
