"""Plain-language review flags, never legal or certification claims."""

from carbon_room import config
from carbon_room.models import CloseSummary


def flags(summary: CloseSummary) -> list[str]:
    settings = config._read_yaml(config._config_dir() / "compliance_checks.yaml")
    messages = settings["flags"]
    result = [settings["disclaimer"]]
    if summary.coverage_pct < 100:
        result.append(messages["incomplete_coverage"])
    if summary.dc_line:
        if summary.dc_line.market_kgco2e == 0:
            result.append(messages["market_zero"])
        result.append(messages["ai_unverified"])
    if config.load_config().get("scope3", {}).get("listed_as_no_data"):
        result.append(messages["scope3_missing"])
    return result
