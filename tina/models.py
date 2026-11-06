"""Validated contracts; all financial inputs must be finite."""
import math
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Quote(Model):
    bid: float = Field(gt=0)
    ask: float = Field(gt=0)
    observed_at: float = Field(gt=0)

    @model_validator(mode="after")
    def ordered(self):
        if self.ask < self.bid:
            raise ValueError("crossed quote")
        return self


class Snapshot(Model):
    observed_at: float = Field(gt=0)
    engine_at: float = Field(gt=0)
    dry_run: Literal[True]
    equity: float = Field(gt=0)
    cash: float = Field(ge=0)
    exposures: dict[str, float]
    quotes: dict[str, Quote]

    @model_validator(mode="after")
    def finite_exposures(self):
        if any(not math.isfinite(v) or v < 0 for v in self.exposures.values()):
            raise ValueError("invalid exposure")
        return self


class Entry(Model):
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    pair: Literal["BTC/EUR", "ETH/EUR"]
    side: Literal["long"] = "long"
    amount: float = Field(gt=0)
    rate: float = Field(gt=0)


class Research(Model):
    pair: Literal["BTC/EUR", "ETH/EUR"]
    source_symbol: Literal["BTC-USD", "ETH-USD"]
    started_at: float = Field(gt=0)
    completed_at: float = Field(gt=0)
    rating: Literal["Buy", "Overweight", "Hold", "Underweight", "Sell", "REVIEW"]
    summary: str = Field(max_length=16000)
    provider: str = Field(max_length=100)
    model: str = Field(max_length=200)

    @model_validator(mode="after")
    def consistent(self):
        expected = {"BTC/EUR": "BTC-USD", "ETH/EUR": "ETH-USD"}
        if expected[self.pair] != self.source_symbol or self.completed_at < self.started_at:
            raise ValueError("inconsistent research identity or timestamps")
        return self
