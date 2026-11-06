"""Immutable process policy; no agent-accessible policy-write endpoint."""
import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Policy:
    max_order: float = 100.0
    max_asset_fraction: float = 0.20
    max_total_fraction: float = 0.40
    risk_fraction: float = 0.005
    daily_loss_fraction: float = 0.02
    drawdown_fraction: float = 0.05
    stop_fraction: float = 0.02
    cost_buffer: float = 0.012  # Illustrative round-trip fee/slippage allowance, not a fee quote.
    max_spread: float = 0.002
    max_price_deviation: float = 0.003
    max_open: int = 2
    max_entries_day: int = 6
    snapshot_ttl: int = 30
    quote_ttl: int = 20
    reservation_ttl: int = 120
    research_ttl: int = 14400
    ai_filter: bool = False


@dataclass(frozen=True)
class Settings:
    database_url: str
    engine_token: str
    read_token: str
    admin_token: str
    research_token: str
    freqtrade_url: str = "http://freqtrade:8080/api/v1"
    freqtrade_user: str = "tina"
    freqtrade_password: str = ""
    poll_seconds: int = 10
    policy: Policy = field(default_factory=Policy)

    @classmethod
    def from_env(cls):
        names = ("ENGINE_TOKEN", "READ_TOKEN", "ADMIN_TOKEN", "RESEARCH_TOKEN")
        values = [os.environ.get("TINA_" + n, "") for n in names]
        if any(len(v) < 32 for v in values) or len(set(values)) != 4:
            raise ValueError("Four distinct TINA_*_TOKEN secrets of at least 32 characters are required")
        mode = os.environ.get("TINA_AI_POLICY", "shadow")
        if mode not in ("shadow", "filter"):
            raise ValueError("TINA_AI_POLICY must be shadow or filter")
        return cls(database_url=os.environ["TINA_DATABASE_URL"], engine_token=values[0],
                   read_token=values[1], admin_token=values[2], research_token=values[3],
                   freqtrade_url=os.environ.get("TINA_FREQTRADE_URL", "http://freqtrade:8080/api/v1"),
                   freqtrade_user=os.environ.get("TINA_FREQTRADE_USER", "tina"),
                   freqtrade_password=os.environ["TINA_FREQTRADE_PASSWORD"],
                   policy=Policy(ai_filter=mode == "filter"))
