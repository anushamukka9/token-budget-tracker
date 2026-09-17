"""Allow ``python -m token_budget_tracker``."""
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
