import yaml

from src.config.loader import find_unknown_settings_keys
from src.models import SettingsConfig


def test_repo_settings_yaml_has_no_ignored_keys():
    with open("config/settings.yaml", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    assert find_unknown_settings_keys(raw, SettingsConfig) == []


def test_misnested_screening_keys_are_reported():
    raw = {"jev": {"enabled": True, "batch_screen_threshold": 0.3}, "screening": {"bogus_key": 1}}
    assert sorted(find_unknown_settings_keys(raw, SettingsConfig)) == [
        "jev.batch_screen_threshold",
        "screening.bogus_key",
    ]
