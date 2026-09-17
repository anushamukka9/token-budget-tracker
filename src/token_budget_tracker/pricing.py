"""Per-model pricing table (USD per 1,000 tokens).

Prices are indicative defaults only (check your provider for current
rates) and are trivially overridden by the user.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from typing import Dict, Iterator, Optional


@dataclass
class ModelPrice:
    """Price for one model, in USD per 1,000 tokens."""

    model: str
    input_per_1k: float
    output_per_1k: float
    notes: str = ""

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * self.input_per_1k + output_tokens * self.output_per_1k) / 1000.0


# Indicative default prices (USD per 1K tokens). Verify with your provider.
_DEFAULT_PRICES = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "o1": (15.00, 60.00),
    "o3-mini": (1.10, 4.40),
    "claude-opus-4": (15.00, 75.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-3-5-haiku": (0.80, 4.00),
    "claude-3-haiku": (0.25, 1.25),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.0-flash": (0.10, 0.40),
    "llama-3.3-70b": (0.35, 0.40),
    "deepseek-v3": (0.27, 1.10),
    "deepseek-r1": (0.55, 2.19),
    "mistral-large": (2.00, 6.00),
}


class UnknownModelError(KeyError):
    """Raised when a model has no entry in the price table."""


class ModelPriceTable:
    """User-extensible per-model price table."""

    def __init__(self, overrides: Optional[Dict[str, ModelPrice]] = None) -> None:
        self._prices: Dict[str, ModelPrice] = {
            name: ModelPrice(name, i, o, notes="built-in default")
            for name, (i, o) in _DEFAULT_PRICES.items()
        }
        if overrides:
            self._prices.update(overrides)

    def add_model(self, model: str, input_per_1k: float, output_per_1k: float,
                  notes: str = "") -> ModelPrice:
        """Add or overwrite a model price."""
        if input_per_1k < 0 or output_per_1k < 0:
            raise ValueError("Prices must be non-negative.")
        price = ModelPrice(model, input_per_1k, output_per_1k, notes=notes)
        self._prices[model] = price
        return price

    def get(self, model: str) -> ModelPrice:
        try:
            return self._prices[model]
        except KeyError:
            raise UnknownModelError(
                f"No price for model {model!r}. Use add_model() to register it."
            ) from None

    def cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("Token counts must be non-negative.")
        return self.get(model).cost(input_tokens, output_tokens)

    def __contains__(self, model: str) -> bool:
        return model in self._prices

    def __iter__(self) -> Iterator[str]:
        return iter(self._prices)

    def __len__(self) -> int:
        return len(self._prices)

    # ---- persistence -------------------------------------------------
    def to_dict(self) -> Dict[str, dict]:
        return {name: asdict(p) for name, p in self._prices.items()}

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2)

    @classmethod
    def load(cls, path: str) -> "ModelPriceTable":
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return cls({name: ModelPrice(**entry) for name, entry in data.items()})
