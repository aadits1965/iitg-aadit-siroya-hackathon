"""Synthetic wholesale banking portfolio generator. All counterparty names are
clearly fictional (rule: no real client data). Fixed seed -> reproducible.
Rating->PD mapping is a documented illustrative assumption (see
docs/ASSUMPTIONS.md), loosely modelled on the shape of published agency
historical default-rate tables but not copied from any single cited source --
stated honestly as illustrative, not sourced.
"""
from __future__ import annotations

import ast
import csv
import random
from dataclasses import asdict, dataclass
from pathlib import Path

SEED = 1234
OUT_PATH = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "portfolio.csv"

RATING_BUCKETS = ["AAA", "AA", "A", "BBB", "BB", "B", "CCC"]

# Illustrative 1-year PD by rating bucket (decimal). NOT sourced from a specific
# published table -- an illustrative, monotonically-increasing-by-notch curve.
RATING_TO_PD = {
    "AAA": 0.0002, "AA": 0.0005, "A": 0.0012, "BBB": 0.0035,
    "BB": 0.0120, "B": 0.0400, "CCC": 0.1500,
}
# Illustrative LGD by seniority (decimal, fraction of EAD lost given default).
LGD_SENIOR_SECURED = 0.35
LGD_SENIOR_UNSECURED = 0.45
LGD_SUBORDINATED = 0.65

SECTORS = ["Technology", "Energy", "Financials", "Industrials", "Healthcare", "Consumer", "Telecom", "Real Estate"]
COUNTRIES = ["US", "UK", "DE", "JP", "BR", "IN", "CN", "AE"]

# Clearly fictional counterparty name components (no real client data, per rule 5/§8-9).
FICTIONAL_PREFIXES = [
    "Northfield", "Stonebridge", "Cedarline", "Brightwater", "Ironvale", "Meridian",
    "Oakhollow", "Silverton", "Redcliff", "Fairmont", "Westbrook", "Highgate",
    "Blackmoor", "Sunriver", "Greywood", "Amberfield", "Thornbury", "Lakeshore",
]
FICTIONAL_SUFFIXES = ["Holdings", "Industries", "Group", "Partners", "Capital", "Energy Corp", "Logistics", "Retail Co"]


@dataclass
class Position:
    position_id: str
    asset_class: str  # loan | bond | swap | option | fx_forward
    counterparty: str
    sector: str
    country: str
    rating: str
    pd: float
    lgd: float
    notional: float
    maturity_years: float
    extra: dict  # asset-class-specific fields (coupon_rate, fixed_rate, strike, etc.)


def _fictional_name(rng: random.Random) -> str:
    return f"{rng.choice(FICTIONAL_PREFIXES)} {rng.choice(FICTIONAL_SUFFIXES)}"


def generate_portfolio(n_positions: int = 50, seed: int = SEED) -> list[Position]:
    rng = random.Random(seed)
    positions: list[Position] = []

    # Rough target mix: 40% loans, 35% bonds, 25% derivatives (swaps/options/fx).
    n_loans = round(n_positions * 0.40)
    n_bonds = round(n_positions * 0.35)
    n_deriv = n_positions - n_loans - n_bonds

    for i in range(n_loans):
        rating = rng.choice(RATING_BUCKETS)
        seniority = rng.choice(["senior_secured", "senior_unsecured"])
        lgd = LGD_SENIOR_SECURED if seniority == "senior_secured" else LGD_SENIOR_UNSECURED
        positions.append(Position(
            position_id=f"LOAN{i+1:03d}",
            asset_class="loan",
            counterparty=_fictional_name(rng),
            sector=rng.choice(SECTORS),
            country=rng.choice(COUNTRIES),
            rating=rating,
            pd=RATING_TO_PD[rating],
            lgd=lgd,
            notional=round(rng.uniform(2_000_000, 50_000_000), -3),
            maturity_years=round(rng.uniform(1, 7), 1),
            extra={"seniority": seniority, "interest_rate": round(rng.uniform(0.04, 0.09), 4)},
        ))

    for i in range(n_bonds):
        is_sovereign = rng.random() < 0.25
        rating = "AAA" if is_sovereign else rng.choice(RATING_BUCKETS[1:])
        positions.append(Position(
            position_id=f"BOND{i+1:03d}",
            asset_class="bond",
            counterparty=("US Treasury" if is_sovereign else _fictional_name(rng)),
            sector=("Sovereign" if is_sovereign else rng.choice(SECTORS)),
            country=("US" if is_sovereign else rng.choice(COUNTRIES)),
            rating=rating,
            pd=RATING_TO_PD[rating],
            lgd=LGD_SENIOR_UNSECURED,
            notional=round(rng.uniform(1_000_000, 30_000_000), -3),
            maturity_years=round(rng.choice([2, 3, 5, 7, 10, 20, 30]), 1),
            extra={
                "coupon_rate": round(rng.uniform(0.03, 0.07), 4),
                "credit_spread_bp": (0 if is_sovereign else round(rng.uniform(50, 450))),
                "is_sovereign": is_sovereign,
            },
        ))

    deriv_types = (["swap"] * 2 + ["option"] * 2 + ["fx_forward"]) * 4
    rng.shuffle(deriv_types)
    for i in range(n_deriv):
        dtype = deriv_types[i % len(deriv_types)]
        rating = rng.choice(RATING_BUCKETS[:5])
        if dtype == "swap":
            extra = {
                "direction": rng.choice(["payer", "receiver"]),
                "fixed_rate": round(rng.uniform(0.03, 0.05), 4),
            }
            maturity = round(rng.choice([2, 3, 5, 7, 10]), 1)
        elif dtype == "option":
            extra = {
                "underlying": rng.choice(["AAPL", "MSFT", "SPY", "NVDA", "JPM"]),
                "option_type": "put",
                "moneyness": round(rng.uniform(0.9, 1.0), 2),  # strike / spot
                "volatility": round(rng.uniform(0.20, 0.45), 2),
            }
            maturity = round(rng.uniform(0.25, 1.5), 2)
        else:
            extra = {"currency_pair": rng.choice(["EURUSD", "GBPUSD", "USDJPY", "USDBRL"]), "fwd_points_bp": round(rng.uniform(-50, 50))}
            maturity = round(rng.uniform(0.1, 1.0), 2)
        positions.append(Position(
            position_id=f"DERIV{i+1:03d}",
            asset_class=dtype,
            counterparty=_fictional_name(rng),
            sector=rng.choice(SECTORS),
            country=rng.choice(COUNTRIES),
            rating=rating,
            pd=RATING_TO_PD[rating],
            lgd=LGD_SENIOR_UNSECURED,
            notional=round(rng.uniform(5_000_000, 40_000_000), -3),
            maturity_years=maturity,
            extra=extra,
        ))

    return positions


def save_portfolio(positions: list[Position], path: Path = OUT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{**asdict(p), "extra": str(p.extra)} for p in positions]
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def load_portfolio(path: Path = OUT_PATH) -> list[Position]:
    positions = []
    with path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            extra = ast.literal_eval(row.pop("extra"))
            positions.append(Position(
                position_id=row["position_id"], asset_class=row["asset_class"],
                counterparty=row["counterparty"], sector=row["sector"], country=row["country"],
                rating=row["rating"], pd=float(row["pd"]), lgd=float(row["lgd"]),
                notional=float(row["notional"]), maturity_years=float(row["maturity_years"]),
                extra=extra,
            ))
    return positions
