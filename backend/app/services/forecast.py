"""Explained production forecast: "How many should we make?" (CONTRACT.md "v3 - Explained production forecast").

Pure, deterministic arithmetic. No language model and no random sampling: every number comes from a closed form
or an exact sum over a probability mass function, so the same inputs always give the same answer.

Model, in four steps:

1. Launch curve (an assumption, not fitted). Pre-orders arrive as a Poisson process whose cumulative intensity
   over the window follows a Bass-diffusion shape:
       F(t) = (1 - e^{-(p+q)t}) / (1 + (q/p) e^{-(p+q)t}),   G(t) = F(t) / F(T)   (t in days, T = window)
   so G(t) is the share of the window's expected pre-orders that should have arrived by time t.
2. Demand level (learned). The window's expected pre-order units Λ get a Gamma prior from "comparable launch"
   parameters, Λ ~ Gamma(α₀ = 1/CV², β₀ = α₀/m₀). Observing U units by time t (exposure G(t)) gives the conjugate
   posterior Λ | data ~ Gamma(α₀ + U, β₀ + G(t)).
3. Predictive demand. Remaining units over an exposure E are Poisson(Λ·E); integrating Λ out gives a negative
   binomial NB(r = α, p = β / (β + E)). Full-season demand is M× the window's level (M = pre-order-to-season
   multiplier, an assumption), so  D = U + NB(α, β / (β + M − G(t))).
4. Newsvendor. Critical ratio CR = (price − cost) / (price − salvage); q* = min{q : P(D ≤ q) ≥ CR};
   recommend max(q*, MOQ). Expected sales use E[min(D, q)] = Σ_{j<q} P(D > j).

Size split: Dirichlet-smoothed shares (n_s + κ·b_s) / (N + κ) toward a base size curve, rounded by largest remainder.

Early-window safeguards (both labelled assumptions, both shown in "How this was calculated"):
* Exposure floor. Right after launch G(t) is close to 0, so two orders at G = 0.003 would read as ~700 per window.
  Until G(t) reaches g_min, the missing exposure (g_min − G) is filled with prior pseudo-orders at the comparable-
  launch rate m₀: α = α₀ + U + m₀·(g_min − G), β = β₀ + g_min. With no orders this is exactly the prior; a handful of
  early orders moves the estimate by their weight against g_min of a window, not against a sliver of it.
* Evidence threshold. No production recommendation is issued until at least `min_window_share_elapsed` of the window
  has passed AND at least `min_orders` orders are in. Before that the forecast says "Too early to recommend" and
  `recommended_quantity` is the planned quantity (the plan the prior is centred on).

Integration seam for the demand data: `orders_for_run(run)` and `window_for_run(run)` are the ONLY places that read
a pipeline run's demand fields: the real Shopify order events (`run.demand.order_events`). v5: there is no
simulated demand - with no orders the forecast says "no orders yet" and shows the labelled assumptions only.

Every assumption is a model parameter, labelled as such and editable (POST /api/forecast with `assumptions`);
they should be fitted to the brand's own past launches.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

from pydantic import Field, field_validator

from ..models import CamelModel
from . import money

METHOD = "gamma-poisson-bass-newsvendor"

DEFAULT_WINDOW_HOURS = 336  # 14 days
DEFAULT_SIZE_CURVE: dict[str, float] = {"XS": 0.08, "S": 0.22, "M": 0.32, "L": 0.24, "XL": 0.14}

# --------------------------------------------------------------------------- wire models


class OrderEvent(CamelModel):
    timestamp: str  # ISO 8601; naive timestamps are read as UTC
    quantity: int = Field(default=1, ge=1, le=10_000)
    size: Optional[str] = None  # size / variant title, e.g. "M"
    unit_price: Optional[float] = Field(default=None, ge=0)
    order_id: Optional[str] = None  # v4: lines of one order share it (counts "sized orders"); not used in the math


class Economics(CamelModel):
    unit_cost: float = Field(gt=0, le=1_000_000)  # landed cost per unit (selected quote's FOB price)
    retail_price: float = Field(gt=0, le=1_000_000)
    salvage_value: Optional[float] = Field(default=None, ge=0, le=1_000_000)  # per unsold unit; default 50% of cost
    moq: int = Field(default=0, ge=0, le=1_000_000)
    fixed_costs: float = Field(default=0.0, ge=0, le=100_000_000)  # e.g. sampling, one-off tooling
    # ISO code the prices above are in (the brand currency). None: numbers are shown without a currency symbol.
    currency: Optional[str] = Field(default=None, pattern=r"^[A-Za-z]{3}$")


class ForecastAssumptions(CamelModel):
    """Every knob that is a judgement call rather than data. Defaults are documented in CONTRACT.md."""

    prior_mean_preorders: float = Field(default=250.0, gt=0, le=1_000_000)  # m₀: comparable launch, units / window
    prior_cv: float = Field(default=0.75, gt=0.05, le=5)  # how unsure we are about m₀ (coefficient of variation)
    bass_p: float = Field(default=0.06, gt=0, le=5)  # innovation (launch spike), per day
    bass_q: float = Field(default=0.25, ge=0, le=5)  # imitation (word of mouth), per day
    season_multiplier: float = Field(default=2.5, ge=1, le=50)  # M: full-season demand / window pre-orders
    size_curve: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_SIZE_CURVE))
    size_prior_strength: float = Field(default=20.0, ge=0, le=100_000)  # κ: pseudo-orders behind the size curve
    unsold_risk_threshold: float = Field(default=0.2, gt=0, lt=1)  # report P(unsold > this share of the run)
    level_cv_floor: float = Field(default=0.12, ge=0, le=2)  # model-uncertainty floor on Λ (shape/multiplier error)
    # Early-window safeguards (see the module docstring). Judgement calls, labelled and editable like the rest.
    min_exposure: float = Field(default=0.05, ge=0, le=1)  # g_min: G(t) counts as at least this share of a window
    min_window_share_elapsed: float = Field(default=0.10, ge=0, le=1)  # time share of the window before recommending
    min_orders: int = Field(default=5, ge=0, le=100_000)  # orders in before recommending

    @field_validator("size_curve")
    @classmethod
    def _curve(cls, v: dict[str, float]) -> dict[str, float]:
        if not v or any(x < 0 for x in v.values()) or sum(v.values()) <= 0:
            raise ValueError("size curve needs at least one size and positive weights")
        return v


class ForecastRequest(CamelModel):
    orders: list[OrderEvent] = Field(default_factory=list, max_length=50_000)
    launch_at: str
    as_of: Optional[str] = None  # default: now, clamped to the window
    window_hours: float = Field(default=DEFAULT_WINDOW_HOURS, gt=0, le=24 * 365)
    economics: Economics
    assumptions: ForecastAssumptions = Field(default_factory=ForecastAssumptions)
    planned_quantity: Optional[int] = Field(default=None, ge=0, le=10_000_000)  # baseline to compare against


class Interval(CamelModel):
    mean: float
    p10: int
    p50: int
    p90: int


class ProjectionPoint(CamelModel):
    hour: float
    mean: float
    p10: int
    p90: int


class ObservedPoint(CamelModel):
    hour: float
    units: int


class SizeLine(CamelModel):
    size: str
    orders: int  # units ordered in this size so far
    base_share: float  # the assumed size curve
    share: float  # Dirichlet-smoothed share
    units: int  # production units for this size


class Outcome(CamelModel):
    quantity: int
    expected_units_sold: float
    expected_leftover: float
    expected_revenue: float  # full-price sales
    expected_salvage: float  # clearance proceeds on leftovers
    expected_cost: float  # production + fixed
    expected_profit: float
    expected_margin: float  # profit / (revenue + salvage)
    stockout_probability: float  # P(D > q)
    fill_rate: float  # E[sold] / E[D]
    unsold_risk_probability: float  # P(leftover > threshold · q)


class ProfitPoint(CamelModel):
    quantity: int
    expected_profit: float


class ExplainStep(CamelModel):
    title: str
    formula: str
    substituted: str
    result: str


class AssumptionItem(CamelModel):
    key: str
    label: str
    value: str
    note: str


class DataUsed(CamelModel):
    order_events: int
    units: int
    sized_units: int
    sized_orders: int = 0  # v4: distinct orders with at least one sized line (events without an order id count 1 each)
    first_order_at: Optional[str] = None
    last_order_at: Optional[str] = None
    span_hours: float
    elapsed_hours: float
    window_hours: float
    window_share_elapsed: float  # G(t): expected share of window pre-orders already in
    avg_order_price: Optional[float] = None


class Explanation(CamelModel):
    summary: str
    steps: list[ExplainStep]
    assumptions: list[AssumptionItem]
    data: DataUsed
    notes: list[str]


class Posterior(CamelModel):
    prior_alpha: float
    prior_beta: float
    alpha: float
    beta: float
    window_level_mean: float  # E[Λ | data]
    data_weight: float  # G / (β₀ + G): how much of the estimate comes from the data vs. the prior


class Evidence(CamelModel):
    """Whether there is enough real demand to recommend a production quantity (both conditions must hold)."""

    ready: bool
    orders: int  # distinct orders in so far
    min_orders: int
    window_share_elapsed: float  # elapsed / window (time, not G(t))
    min_window_share_elapsed: float
    note: str


class Forecast(CamelModel):
    method: str = METHOD
    llm_used: bool = False
    confidence: Literal["prior-only", "early", "firming", "data-driven"]
    confidence_note: str
    # "too_early": the evidence threshold is not met; recommended_quantity is then the planned quantity (the plan
    # the prior is centred on), and `newsvendor_quantity` is what the maths would say on the evidence so far.
    recommendation_status: Literal["too_early", "recommended"] = "recommended"
    evidence: Optional[Evidence] = None
    currency: Optional[str] = None  # the currency of every money figure (the brand currency)
    recommended_quantity: int
    newsvendor_quantity: Optional[int] = None  # max(q*, MOQ) - equals recommended_quantity once ready
    unconstrained_quantity: int  # newsvendor q* before MOQ
    moq: int
    moq_binding: bool
    moq_note: Optional[str] = None
    critical_ratio: float
    underage_cost: float  # p − c: margin lost per unit of unmet demand
    overage_cost: float  # c − s: loss per unsold unit
    unit_cost: float
    retail_price: float
    salvage_value: float
    fixed_costs: float
    preorders: Interval  # by end of window (observed + remaining)
    season: Interval  # full-season demand D
    observed_units: int
    outcome: Outcome
    baseline: Optional[Outcome] = None  # at planned_quantity, when given
    profit_delta_vs_baseline: Optional[float] = None
    sizes: list[SizeLine]
    projection: list[ProjectionPoint]
    observed: list[ObservedPoint]
    profit_curve: list[ProfitPoint]
    posterior: Posterior
    explanation: Explanation
    inputs: ForecastRequest  # normalised echo, so a client can POST it back with tweaked assumptions
    as_of: str
    launch_at: str


# --------------------------------------------------------------------------- maths


def bass_cdf(t_days: float, p: float, q: float) -> float:
    """Bass diffusion cumulative adoption share F(t); F(0) = 0, increasing to 1."""
    if t_days <= 0:
        return 0.0
    e = math.exp(-(p + q) * t_days)
    return (1.0 - e) / (1.0 + (q / p) * e)


def launch_share(hour: float, window_hours: float, p: float, q: float) -> float:
    """G(t) = F(t) / F(T): expected share of the window's pre-orders in by `hour` (clamped to [0, 1])."""
    h = min(max(hour, 0.0), window_hours)
    return bass_cdf(h / 24.0, p, q) / bass_cdf(window_hours / 24.0, p, q)


# The exact pmf table grows with the demand it describes. Review finding (17 Oct): a prior mean of 250,000 used 1.5 GB
# in one request. 300,000 entries (~30 MB, well under a second) covers demand far beyond a small brand's runs; past it
# the forecast is refused before anything is allocated.
MAX_TABLE = 300_000
# Observed pre-order units the forecast will take. Anything beyond it is not a small brand's pre-order window, and the
# posterior tables it implies would exhaust memory (audit, 17 Oct: 20,000 orders x 10,000 units froze the server).
MAX_OBSERVED_UNITS = 1_000_000


class NegBinom:
    """Negative binomial NB(r, p) on k = 0, 1, …: pmf(k) = Γ(k+r)/(k! Γ(r)) p^r (1-p)^k. Exact pmf table."""

    def __init__(self, r: float, p: float):
        self.r, self.p = r, p
        if p >= 1.0 or r <= 0:
            self.pmf = [1.0]
        else:
            mean = r * (1 - p) / p
            sd = math.sqrt(r * (1 - p)) / p
            kmax = int(mean + 14 * sd + 30)
            if kmax > MAX_TABLE:
                raise ValueError(f"demand this large ({mean:,.0f} units expected) is outside what the forecast "
                                 "computes exactly - lower the prior mean, its uncertainty or the season multiplier")
            logp, log1p = r * math.log(p), math.log1p(-p)
            pmf, lp = [], logp
            for k in range(kmax + 1):
                pmf.append(math.exp(lp))
                lp += math.log((k + r) / (k + 1)) + log1p
            total = sum(pmf)
            self.pmf = [x / total for x in pmf]  # renormalise the (negligible) truncated tail
        cdf, acc = [], 0.0
        for x in self.pmf:
            acc += x
            cdf.append(acc)
        cdf[-1] = 1.0
        self.cdf = cdf

    @property
    def mean(self) -> float:
        return sum(k * x for k, x in enumerate(self.pmf))

    def quantile(self, prob: float) -> int:
        """Smallest k with P(X ≤ k) ≥ prob."""
        lo, hi = 0, len(self.cdf) - 1
        target = prob - 1e-12
        while lo < hi:
            mid = (lo + hi) // 2
            if self.cdf[mid] >= target:
                hi = mid
            else:
                lo = mid + 1
        return lo

    def cdf_at(self, k: int) -> float:
        if k < 0:
            return 0.0
        return self.cdf[min(k, len(self.cdf) - 1)]


def predictive(alpha: float, beta: float, exposure: float) -> NegBinom:
    """Units over a further `exposure` (in window-level units) given Λ ~ Gamma(alpha, beta)."""
    if exposure <= 0:
        return NegBinom(alpha, 1.0)
    return NegBinom(alpha, beta / (beta + exposure))


def critical_ratio(price: float, cost: float, salvage: float) -> float:
    """CR = (p − c) / (p − s): underage cost over underage + overage cost."""
    return (price - cost) / (price - salvage)


def largest_remainder(shares: dict[str, float], total: int) -> dict[str, int]:
    """Integers proportional to `shares` that sum exactly to `total` (Hamilton / largest-remainder method)."""
    s = sum(shares.values())
    if total <= 0 or s <= 0:
        return {k: 0 for k in shares}
    raw = {k: total * v / s for k, v in shares.items()}
    out = {k: int(math.floor(x)) for k, x in raw.items()}
    left = total - sum(out.values())
    order = sorted(shares, key=lambda k: (-(raw[k] - out[k]), -shares[k], list(shares).index(k)))
    for k in order[:left]:
        out[k] += 1
    return out


class _Demand:
    """D = U + R with R ~ NB: helpers for newsvendor maths on the shifted distribution."""

    def __init__(self, observed: int, rest: NegBinom):
        self.u, self.rest = observed, rest
        self.mean = observed + rest.mean

    def cdf(self, d: int) -> float:
        return self.rest.cdf_at(d - self.u)

    def quantile(self, prob: float) -> int:
        return self.u + self.rest.quantile(prob)

    def expected_sales(self, q: int) -> float:
        """E[min(D, q)] = Σ_{j<q} P(D > j)."""
        if q <= 0:
            return 0.0
        m = min(q, self.u)
        tail = 0.0
        for j in range(self.u, q):  # P(D > j) = 1 for j < U
            tail += 1.0 - self.cdf(j)
        return m + tail


def _outcome(dem: _Demand, q: int, price: float, cost: float, salvage: float, fixed: float, risk: float) -> Outcome:
    sold = dem.expected_sales(q)
    left = q - sold
    revenue, salvage_rev, spend = price * sold, salvage * left, cost * q + fixed
    profit = revenue + salvage_rev - spend
    unsold_cut = math.ceil(q * (1 - risk)) - 1  # leftover > risk·q  <=>  D < q(1 − risk)  <=>  D ≤ ⌈q(1−risk)⌉ − 1
    return Outcome(
        quantity=q,
        expected_units_sold=round(sold, 2),
        expected_leftover=round(left, 2),
        expected_revenue=round(revenue, 2),
        expected_salvage=round(salvage_rev, 2),
        expected_cost=round(spend, 2),
        expected_profit=round(profit, 2),
        expected_margin=round(profit / (revenue + salvage_rev), 4) if revenue + salvage_rev > 0 else 0.0,
        stockout_probability=round(1.0 - dem.cdf(q), 4),
        fill_rate=round(sold / dem.mean, 4) if dem.mean > 0 else 1.0,
        unsold_risk_probability=round(dem.cdf(unsold_cut) if q > 0 else 0.0, 4),
    )


# --------------------------------------------------------------------------- time helpers


def _parse(ts: str) -> datetime:
    d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _f(x: float, d: int = 2) -> str:
    return f"{x:,.{d}f}"




# --------------------------------------------------------------------------- the forecast


def forecast(req: ForecastRequest, *, now: Optional[datetime] = None) -> Forecast:
    a, econ = req.assumptions, req.economics
    ccy = econ.currency.upper() if econ.currency else None

    def _money(x: float, d: int = 2) -> str:  # every money figure in the brand currency
        return money.fmt(x, ccy, d)
    T = float(req.window_hours)
    launch = _parse(req.launch_at)
    if req.as_of:
        as_of = _parse(req.as_of)
    else:
        as_of = min(now or datetime.now(timezone.utc), launch + timedelta(hours=T))
    elapsed = min(max((as_of - launch).total_seconds() / 3600.0, 0.0), T)

    # ---- data: orders inside the window up to as_of
    events = sorted(
        ((max(0.0, (_parse(o.timestamp) - launch).total_seconds() / 3600.0), o) for o in req.orders),
        key=lambda x: x[0],
    )
    events = [(h, o) for h, o in events if h <= elapsed + 1e-9]
    U = sum(o.quantity for _, o in events)
    if U > MAX_OBSERVED_UNITS:
        raise ValueError(f"{U:,} pre-order units is outside what the forecast computes exactly (at most "
                         f"{MAX_OBSERVED_UNITS:,}) - check the orders list")
    priced = [(o.unit_price, o.quantity) for _, o in events if o.unit_price is not None]
    avg_price = (sum(p * n for p, n in priced) / sum(n for _, n in priced)) if priced else None

    # ---- 1. launch curve
    G = launch_share(elapsed, T, a.bass_p, a.bass_q)
    M = a.season_multiplier

    # ---- 2. prior + posterior on the window level Λ
    a0 = 1.0 / (a.prior_cv ** 2)
    b0 = a0 / a.prior_mean_preorders
    g_min = a.min_exposure
    pad = max(0.0, g_min - G)  # missing early exposure, filled with prior pseudo-orders at rate m₀
    exposure = G + pad
    # The floor tempers the mean only; the shape stays α₀ + U, so the padding adds no false certainty.
    level = (a0 + U + a.prior_mean_preorders * pad) / (b0 + exposure)
    alpha = a0 + U
    beta = alpha / level
    alpha_cap = 1.0 / a.level_cv_floor ** 2 if a.level_cv_floor > 0 else math.inf
    floored = alpha > alpha_cap
    if floored:  # keep the mean, widen to the floor: the curve shape and M are assumed, so data can't buy certainty
        alpha, beta = alpha_cap, alpha_cap / level
    data_weight = G / (b0 + exposure) if G > 0 else 0.0

    # ---- 3. predictive distributions
    rest_window = predictive(alpha, beta, 1.0 - G)
    rest_season = predictive(alpha, beta, max(M - G, 0.0))
    window_d = _Demand(U, rest_window)
    season_d = _Demand(U, rest_season)

    def interval(dd: _Demand) -> Interval:
        return Interval(mean=round(dd.mean, 1), p10=dd.quantile(0.10), p50=dd.quantile(0.50), p90=dd.quantile(0.90))

    pre_iv, season_iv = interval(window_d), interval(season_d)

    # ---- 4. newsvendor
    price, cost = econ.retail_price, econ.unit_cost
    salvage = econ.salvage_value if econ.salvage_value is not None else round(0.5 * cost, 2)
    notes: list[str] = []
    salvage_eff = salvage
    if salvage_eff >= cost:
        salvage_eff = cost * 0.999
        notes.append("Salvage value is at or above unit cost, so an unsold unit costs nothing: the newsvendor would "
                     "make unlimited stock. Salvage was capped just below cost for the maths.")
    under, over = price - cost, cost - salvage_eff
    if under <= 0:
        cr, q_star = 0.0, 0
        notes.append("Retail price does not cover unit cost: every unit sold loses money, so the newsvendor "
                     "quantity is zero. Re-price or re-source before producing.")
    else:
        cr = critical_ratio(price, cost, salvage_eff)
        q_star = season_d.quantile(cr)
    q_nv = max(q_star, econ.moq)
    moq_binding = econ.moq > q_star

    # ---- evidence threshold: no production call on a sliver of the window or a couple of orders
    distinct_orders = len({o.order_id or f"#event-{i}" for i, (_, o) in enumerate(events)})
    share_elapsed = elapsed / T if T > 0 else 1.0
    ready = share_elapsed + 1e-9 >= a.min_window_share_elapsed and distinct_orders >= a.min_orders
    plan = req.planned_quantity if req.planned_quantity is not None else None
    q = q_nv if ready or plan is None else max(plan, econ.moq)
    if ready:
        ev_note = (f"{distinct_orders:,} order{'s' if distinct_orders != 1 else ''} over {share_elapsed:.0%} of the "
                   f"window - enough to recommend (needs ≥ {a.min_orders:,} orders and ≥ "
                   f"{a.min_window_share_elapsed:.0%} of the window).")
    else:
        missing = []
        if distinct_orders < a.min_orders:
            missing.append(f"{a.min_orders - distinct_orders:,} more order{'s' if a.min_orders - distinct_orders != 1 else ''}")
        if share_elapsed + 1e-9 < a.min_window_share_elapsed:
            missing.append(f"{a.min_window_share_elapsed:.0%} of the window to pass ({share_elapsed:.1%} so far)")
        ev_note = (f"Too early to recommend - collecting orders ({distinct_orders:,} so far). Needs "
                   + " and ".join(missing) + "."
                   + (f" Until then the plan stands: {plan:,} units." if plan is not None else ""))
    evidence = Evidence(ready=ready, orders=distinct_orders, min_orders=a.min_orders,
                        window_share_elapsed=round(share_elapsed, 4),
                        min_window_share_elapsed=a.min_window_share_elapsed, note=ev_note)
    risk = a.unsold_risk_threshold
    out = _outcome(season_d, q, price, cost, salvage_eff, econ.fixed_costs, risk)
    moq_note = None
    if moq_binding:
        at_star = _outcome(season_d, q_star, price, cost, salvage_eff, econ.fixed_costs, risk)
        at_moq = out if q == q_nv else _outcome(season_d, q_nv, price, cost, salvage_eff, econ.fixed_costs, risk)
        moq_note = (f"The supplier MOQ of {econ.moq:,} binds: the profit-maximising run is {q_star:,}, so "
                    f"{econ.moq - q_star:,} extra units are made. That costs about "
                    f"{_money(at_star.expected_profit - at_moq.expected_profit, 0)} of expected profit.")
        if at_moq.expected_profit < 0:
            moq_note += " At the MOQ the expected profit is negative - consider a mill with a lower MOQ."

    baseline, delta = None, None
    if req.planned_quantity is not None:
        baseline = _outcome(season_d, req.planned_quantity, price, cost, salvage_eff, econ.fixed_costs, risk)
        delta = round(out.expected_profit - baseline.expected_profit, 2)

    # ---- profit curve E[π(q)], sampled for the chart (π(q+1) − π(q) = (p − s)·P(D > q) − (c − s))
    q_hi = max(season_iv.p90, q, req.planned_quantity or 0, 1)
    q_hi = int(q_hi * 1.25) + 5
    curve: list[ProfitPoint] = []
    sold = 0.0
    stride = max(1, q_hi // 60)
    for k in range(q_hi + 1):
        if k % stride == 0 or k == q_hi:
            prof = price * sold + salvage_eff * (k - sold) - cost * k - econ.fixed_costs
            curve.append(ProfitPoint(quantity=k, expected_profit=round(prof, 2)))
        sold += 1.0 - season_d.cdf(k)

    # ---- size split
    base_total = sum(a.size_curve.values())
    base = {k: v / base_total for k, v in a.size_curve.items()}
    by_upper = {k.strip().upper(): k for k in base}  # "m" from a storefront counts toward the curve's "M"
    counts: dict[str, int] = {}
    sized_ids: set[str] = set()
    for i, (_, o) in enumerate(events):
        if o.size and o.size.strip():
            key = by_upper.get(o.size.strip().upper(), o.size.strip())
            counts[key] = counts.get(key, 0) + o.quantity
            sized_ids.add(o.order_id or f"#event-{i}")
    sizes_all = list(base) + [s for s in counts if s not in base]
    N = sum(counts.values())
    kappa = a.size_prior_strength
    shares = {s: (counts.get(s, 0) + kappa * base.get(s, 0.0)) / (N + kappa) if N + kappa > 0 else base.get(s, 0.0)
              for s in sizes_all}
    units = largest_remainder(shares, q)
    sizes = [SizeLine(size=s, orders=counts.get(s, 0), base_share=round(base.get(s, 0.0), 4),
                      share=round(shares[s], 4), units=units[s]) for s in sizes_all]

    # ---- projection fan (cumulative pre-orders over the window)
    proj: list[ProjectionPoint] = []
    hours = sorted({round(elapsed, 2), *[round(T * i / 28, 2) for i in range(29) if T * i / 28 > elapsed]})
    for h in hours:
        dd = _Demand(U, predictive(alpha, beta, launch_share(h, T, a.bass_p, a.bass_q) - G))
        proj.append(ProjectionPoint(hour=h, mean=round(dd.mean, 1), p10=dd.quantile(0.1), p90=dd.quantile(0.9)))
    observed: list[ObservedPoint] = [ObservedPoint(hour=0, units=0)]
    cum = 0
    for h, o in events:
        cum += o.quantity
        observed.append(ObservedPoint(hour=round(h, 2), units=cum))
    if observed[-1].hour < elapsed:
        observed.append(ObservedPoint(hour=round(elapsed, 2), units=cum))

    # ---- confidence, plainly
    rel = (season_iv.p90 - season_iv.p10) / max(season_iv.mean, 1.0)
    if not ready:
        notes.insert(0, ev_note)
    if pad > 0 and U > 0:
        notes.append(f"Only {G:.1%} of the window's expected orders would normally be in by now, below the "
                     f"{g_min:.0%} exposure floor: the gap is filled with the comparable-launch rate, so these early "
                     f"orders are not extrapolated across the whole window.")
    if U == 0:
        confidence = "prior-only"
        cnote = (f"No orders yet. This is the comparable-launch assumption (≈{a.prior_mean_preorders:,.0f} pre-orders "
                 f"per window), not a forecast from your data - the interval is deliberately wide.")
    elif U < 20 or data_weight < 0.5:
        confidence = "early"
        cnote = (f"Only {U:,} unit{'s' if U != 1 else ''} ordered so far, so the prior still matters and the "
                 f"80% interval spans ±{rel / 2:.0%} of the mean. It will narrow as orders arrive.")
    elif rel > 0.5:
        confidence = "firming"
        cnote = f"{U:,} units in; the estimate is mostly data now, but the 80% interval is still ±{rel / 2:.0%}."
    else:
        confidence = "data-driven"
        cnote = f"{U:,} units in; the forecast is driven by your orders (80% interval ±{rel / 2:.0%} of the mean)."
    if G < 1 and U > 0:
        notes.append("The launch-curve shape is assumed, not fitted: only its scale is learned from the orders. "
                     "If word of mouth is stronger or weaker than assumed, the projection shifts accordingly.")
    if any(o.quantity > 1 for _, o in events):
        notes.append("Units are modelled as Poisson arrivals; multi-unit orders make real demand slightly more "
                     "variable than the interval suggests.")
    notes.append("The labelled assumptions (comparable launch, launch-curve shape, season multiplier, size curve, "
                 "clearance value) are model parameters, not data: fit them to the brand's own past launches and edit "
                 "them here.")

    # ---- explanation
    t_days = elapsed / 24
    steps = [
        ExplainStep(
            title="Launch curve (how far through the window we are)",
            formula="G(t) = F(t) / F(T),  F(t) = (1 − e^{−(p+q)t}) / (1 + (q/p)·e^{−(p+q)t})",
            substituted=f"p = {a.bass_p}, q = {a.bass_q} per day, t = {t_days:.2f} d, T = {T / 24:.2f} d",
            result=f"G(t) = {G:.3f} - {G:.0%} of the window's pre-orders would normally be in by now",
        ),
        ExplainStep(
            title="Prior from comparable launches",
            formula="Λ ~ Gamma(α₀, β₀),  α₀ = 1/CV²,  β₀ = α₀ / m₀",
            substituted=f"m₀ = {a.prior_mean_preorders:,.0f} units, CV = {a.prior_cv}",
            result=f"α₀ = {a0:.3f}, β₀ = {b0:.5f}",
        ),
        ExplainStep(
            title="Update with the orders received (Gamma–Poisson)",
            formula=("E[Λ] = (α₀ + U + m₀·max(0, g_min − G)) / (β₀ + max(G, g_min)),  α = α₀ + U,  "
                     "β = α / E[Λ]"),
            substituted=(f"U = {U:,} units, G(t) = {G:.3f}, g_min = {g_min:g}"
                         + (f" → {pad:.3f} of a window filled with {a.prior_mean_preorders * pad:,.1f} prior "
                            f"pseudo-orders (exposure floor)" if pad > 0 else " (exposure floor not binding)")),
            result=(f"α = {a0 + U:.2f}, β = {(a0 + U) / level:.4f}, E[Λ] = {level:,.1f} pre-orders per window "
                    f"({data_weight:.0%} data, {1 - data_weight:.0%} prior)"
                    + (f"; uncertainty floored at CV {a.level_cv_floor} (α → {alpha:.1f}, β → {beta:.4f})"
                       if floored else "")),
        ),
        ExplainStep(
            title="Pre-orders by the end of the window",
            formula="U + NB(r = α, p = β / (β + 1 − G))",
            substituted=f"{U:,} + NB({alpha:.2f}, {beta / (beta + 1 - G) if G < 1 else 1:.4f})",
            result=f"mean {pre_iv.mean:,.0f}, 80% interval {pre_iv.p10:,}–{pre_iv.p90:,}",
        ),
        ExplainStep(
            title="Full-season demand",
            formula="D = U + NB(r = α, p = β / (β + M − G))",
            substituted=f"M = {M} (season ÷ pre-orders), {U:,} + NB({alpha:.2f}, {beta / (beta + M - G):.4f})",
            result=f"mean {season_iv.mean:,.0f}, 80% interval {season_iv.p10:,}–{season_iv.p90:,}",
        ),
        ExplainStep(
            title="Critical ratio (newsvendor)",
            formula="CR = (p − c) / (p − s) = underage / (underage + overage)",
            substituted=f"({_money(price)} − {_money(cost)}) / ({_money(price)} − {_money(salvage_eff)})",
            result=f"CR = {cr:.3f} - stock up to the {cr:.0%} quantile of demand",
        ),
        ExplainStep(
            title="Optimal run",
            formula="q* = min{ q : P(D ≤ q) ≥ CR },  q = max(q*, MOQ)",
            substituted=(f"P(D ≤ {q_star - 1:,}) = {season_d.cdf(q_star - 1):.4f} < {cr:.4f} ≤ "
                         f"P(D ≤ {q_star:,}) = {season_d.cdf(q_star):.4f}, MOQ = {econ.moq:,}"),
            result=f"q* = {q_star:,} → make {q_nv:,}" + (" (MOQ binds)" if moq_binding else ""),
        ),
        ExplainStep(
            title="Enough evidence to recommend?",
            formula="recommend only if elapsed / T ≥ s_min  and  orders ≥ n_min; otherwise keep the plan",
            substituted=(f"elapsed / T = {share_elapsed:.3f} (s_min = {a.min_window_share_elapsed:g}), orders = "
                         f"{distinct_orders:,} (n_min = {a.min_orders:,})"),
            result=(f"yes - make {q:,}" if ready else
                    f"not yet - the plan stands at {q:,}" + (f" (the maths so far would say {q_nv:,})"
                                                            if q_nv != q else "")),
        ),
        ExplainStep(
            title="Expected outcome at that run",
            formula="E[sold] = Σ_{j<q} P(D > j),  E[π] = p·E[sold] + s·(q − E[sold]) − c·q − F",
            substituted=(f"{_money(price)}×{out.expected_units_sold:,.1f} + {_money(salvage_eff)}×"
                         f"{out.expected_leftover:,.1f} − {_money(cost)}×{q:,} − {_money(econ.fixed_costs, 0)}"),
            result=(f"E[profit] = {_money(out.expected_profit, 0)}, margin {out.expected_margin:.1%}, "
                    f"P(stock-out) {out.stockout_probability:.0%}"),
        ),
        ExplainStep(
            title="Size split",
            formula="share_s = (n_s + κ·b_s) / (N + κ),  units by largest remainder (sums to q)",
            substituted=f"N = {N:,} sized units from {len(sized_ids):,} orders, κ = {kappa:g}",
            result=", ".join(f"{s.size} {s.units:,}" for s in sizes),
        ),
    ]
    assumptions = [
        AssumptionItem(key="priorMeanPreorders", label="Comparable launch: pre-orders per window",
                       value=f"{a.prior_mean_preorders:,.0f} units", note="Prior centre m₀. For a run it defaults to the planned quantity ÷ season multiplier. A judgement, not data."),
        AssumptionItem(key="priorCv", label="Uncertainty about that comparable",
                       value=f"CV {a.prior_cv}", note="Higher = weaker prior, data takes over sooner."),
        AssumptionItem(key="bassP", label="Launch spike (Bass p)", value=f"{a.bass_p}/day",
                       note="Share of buyers who come from the launch itself (email list, ads)."),
        AssumptionItem(key="bassQ", label="Word of mouth (Bass q)", value=f"{a.bass_q}/day",
                       note="How strongly early buyers pull in later ones. Shape only; scale is learned."),
        AssumptionItem(key="seasonMultiplier", label="Pre-order → season multiplier",
                       value=f"{M}×", note=f"Full-season demand assumed {M}× the pre-order window "
                                           f"(pre-orders ≈ {1 / M:.0%} of the season)."),
        AssumptionItem(key="salvageValue", label="Clearance value per unsold unit", value=_money(salvage_eff),
                       note="Default 50% of unit cost (off-price / outlet)." if econ.salvage_value is None
                       else "Set by you."),
        AssumptionItem(key="sizeCurve", label="Base size curve",
                       value=" · ".join(f"{k} {v:.0%}" for k, v in base.items()),
                       note=f"Blended with real size mix; worth κ = {kappa:g} orders."),
        AssumptionItem(key="levelCvFloor", label="Model-uncertainty floor", value=f"CV ≥ {a.level_cv_floor}",
                       note="Even with many orders the curve shape and multiplier are assumptions, so the demand "
                            "level is never treated as known more precisely than this."),
        AssumptionItem(key="unsoldRiskThreshold", label="Unsold-stock risk line", value=f"> {risk:.0%} of the run",
                       note="Reported as a probability; does not change the recommendation."),
        AssumptionItem(key="minExposure", label="Early-window exposure floor", value=f"G ≥ {g_min:g}",
                       note="Until this share of the window's expected orders would normally be in, the gap is "
                            "filled with prior pseudo-orders, so a few launch-day orders can't be extrapolated "
                            "across the whole window."),
        AssumptionItem(key="minWindowShareElapsed", label="Evidence threshold: window elapsed",
                       value=f"≥ {a.min_window_share_elapsed:.0%} of the window",
                       note="No production recommendation before this much of the window has passed."),
        AssumptionItem(key="minOrders", label="Evidence threshold: orders", value=f"≥ {a.min_orders:,} orders",
                       note="No production recommendation before this many orders are in; until then the plan "
                            "stands."),
    ]
    first = events[0][1].timestamp if events else None
    last = events[-1][1].timestamp if events else None
    data = DataUsed(
        order_events=len(events), units=U, sized_units=N, sized_orders=len(sized_ids), first_order_at=first,
        last_order_at=last,
        span_hours=round(events[-1][0] - events[0][0], 2) if events else 0.0,
        elapsed_hours=round(elapsed, 2), window_hours=T, window_share_elapsed=round(G, 4),
        avg_order_price=round(avg_price, 2) if avg_price is not None else None,
    )
    lead = f"Make {q:,} units." if ready else (f"Too early to recommend - collecting orders "
                                               f"({distinct_orders:,} so far); the plan stands at {q:,} units.")
    summary = (f"{lead} Full-season demand is projected at {season_iv.mean:,.0f} "
               f"(80%: {season_iv.p10:,}–{season_iv.p90:,}) from {U:,} pre-order unit{'s' if U != 1 else ''} "
               f"{t_days:.1f} days into a {T / 24:.0f}-day window; with a {_money(price, 0)} price, "
               f"{_money(cost)} cost and {_money(salvage_eff)} clearance value the newsvendor stocks to the "
               f"{cr:.0%} demand quantile.")

    inputs = req.model_copy(deep=True)
    inputs.as_of = _iso(as_of)
    return Forecast(
        confidence=confidence, confidence_note=cnote,
        recommendation_status="recommended" if ready else "too_early", evidence=evidence, currency=ccy,
        recommended_quantity=q, newsvendor_quantity=q_nv, unconstrained_quantity=q_star, moq=econ.moq, moq_binding=moq_binding,
        moq_note=moq_note, critical_ratio=round(cr, 4), underage_cost=round(under, 2), overage_cost=round(over, 2),
        unit_cost=cost, retail_price=price, salvage_value=round(salvage_eff, 2), fixed_costs=econ.fixed_costs,
        preorders=pre_iv, season=season_iv, observed_units=U, outcome=out, baseline=baseline,
        profit_delta_vs_baseline=delta, sizes=sizes, projection=proj, observed=observed, profit_curve=curve,
        posterior=Posterior(prior_alpha=round(a0, 4), prior_beta=round(b0, 6), alpha=round(alpha, 4),
                            beta=round(beta, 6), window_level_mean=round(level, 2),
                            data_weight=round(data_weight, 4)),
        explanation=Explanation(summary=summary, steps=steps, assumptions=assumptions, data=data, notes=notes),
        inputs=inputs, as_of=_iso(as_of), launch_at=_iso(launch),
    )


# --------------------------------------------------------------------------- integration seam (pipeline runs)


def _field(obj: Any, *names: str) -> Any:
    for n in names:
        v = obj.get(n) if isinstance(obj, dict) else getattr(obj, n, None)
        if v is not None:
            return v
    return None


def _real_order_list(demand: Any) -> Optional[list]:
    """The real-orders list on the demand model (`order_events`, or `orders` as a list / `events`), if present.

    """
    for name in ("orders", "events", "order_events", "orderEvents"):
        v = demand.get(name) if isinstance(demand, dict) else getattr(demand, name, None)
        if isinstance(v, list):
            return v
    return None


def window_for_run(run: Any) -> tuple[datetime, datetime, float]:
    """(launch, as_of, window_hours) for a run's pre-order window. See CONTRACT.md "v3" for the precedence."""
    d = run.demand
    window = float(_field(d, "window_hours") or DEFAULT_WINDOW_HOURS)
    launch_s = _field(d, "launched_at", "launch_at", "started_at", "opened_at")
    if launch_s is None:
        step = next((s for s in run.steps if s.key == "preorder_demand"), None)
        launch_s = (step.started_at if step else None) or run.created_at
    launch = _parse(launch_s)
    elapsed = _field(d, "elapsed_hours")
    if _real_order_list(d) is None or (elapsed and float(elapsed) > 0):
        as_of = launch + timedelta(hours=min(float(elapsed or 0.0), window))
    else:
        as_of = min(datetime.now(timezone.utc), launch + timedelta(hours=window))
    return launch, as_of, window


def orders_for_run(run: Any) -> list[OrderEvent]:
    """THE seam: a run's pre-orders as OrderEvents.

    - Real orders (future): if `run.demand.orders` (or `events` / `orderEvents`) is a list, each item (dict or model)
      is read for timestamp (`timestamp` | `createdAt` | `created_at` | `processedAt`), quantity (`quantity`, default
      1), size (`size` | `variant` | `variantTitle` | `variant_title`) and price (`unitPrice` | `unit_price` | `price`).
    """
    d = run.demand
    if d is None:
        return []
    real = _real_order_list(d)
    out: list[OrderEvent] = []
    if real is not None:
        for item in real:
            ts = _field(item, "timestamp", "createdAt", "created_at", "processedAt", "processed_at")
            if ts is None:
                continue
            qty = _field(item, "quantity", "qty") or 1
            size = _field(item, "size", "variant", "variantTitle", "variant_title", "option1")
            price = _field(item, "unitPrice", "unit_price", "price")
            oid = _field(item, "order_id", "orderId")
            try:
                out.append(OrderEvent(timestamp=ts if isinstance(ts, str) else _iso(ts), quantity=max(1, int(qty)),
                                      size=str(size) if size is not None else None,
                                      unit_price=float(price) if price is not None else None,
                                      order_id=str(oid) if oid is not None else None))
            except (ValueError, TypeError):
                continue
        return out
    return out


def size_curve_for(sizes: Optional[list[str]]) -> dict[str, float]:
    """v4: the base size curve restricted / extended to the sizes the product is really sold in.

    Sizes on the default curve keep their weight; any other size (XXL, 3XL, numeric sizes) gets the curve's
    smallest weight, so it is possible but not assumed popular. Renormalised to 1. None / [] -> the default."""
    if not sizes:
        return dict(DEFAULT_SIZE_CURVE)
    upper = {k.upper(): v for k, v in DEFAULT_SIZE_CURVE.items()}
    floor = min(DEFAULT_SIZE_CURVE.values())
    raw = {s: upper.get(s.strip().upper(), floor) for s in dict.fromkeys(sizes) if s and s.strip()}
    total = sum(raw.values())
    return {k: round(v / total, 4) for k, v in raw.items()} if total > 0 else dict(DEFAULT_SIZE_CURVE)


def _plan_anchored_assumptions(planned_quantity: int, sizes: Optional[list[str]] = None) -> ForecastAssumptions:
    """Centre the prior on the brand's own plan: window pre-orders m₀ = planned run ÷ season multiplier.

    With no orders yet the forecast then reproduces the plan's demand level instead of a generic comparable,
    and real orders move it from there.
    """
    base = ForecastAssumptions(size_curve=size_curve_for(sizes))
    if planned_quantity and planned_quantity > 0:
        base.prior_mean_preorders = max(1.0, planned_quantity / base.season_multiplier)
    return base


def _run_sizes(run: Any) -> Optional[list[str]]:
    """The sizes the run's product is sold in: the Shopify variants, else the tech pack's size range."""
    p = getattr(run, "shopify_product", None)
    if p is not None and getattr(p, "sizes", None):
        return list(p.sizes)
    if getattr(run, "tech_pack", None) is not None:
        from . import sizes as _sizes

        return _sizes.size_range(run.tech_pack)
    return None


def request_for_run(run: Any, assumptions: Optional[ForecastAssumptions] = None) -> ForecastRequest:
    """Build a ForecastRequest from a run: selected quote (unit cost, MOQ, sample cost), retail price, orders."""
    from . import sourcing  # local import keeps this module importable on its own

    tp = run.tech_pack
    if tp is None:
        raise ValueError("the tech pack has not been generated yet")
    q = sourcing.selected_quote(run.quotes, run.recommendation)
    unit = q.unit_price if (q and q.unit_price) else sourcing.unit_cost(tp)  # the model's costing until a quote
    p = run.shopify_product  # the brand-currency retail (the store may list in another currency)
    price = (p.price_brand if p is not None and p.price_brand is not None else
             p.price if p is not None and p.fx_rate is None else tp.target_retail_price)
    ccy = tp.currency or money.brand_currency()  # the quote's unit_price is already in the brand currency
    launch, as_of, window = window_for_run(run) if run.demand else (
        datetime.now(timezone.utc), datetime.now(timezone.utc), float(DEFAULT_WINDOW_HOURS))
    return ForecastRequest(
        orders=orders_for_run(run), launch_at=_iso(launch), as_of=_iso(as_of), window_hours=window,
        economics=Economics(unit_cost=unit, retail_price=price, moq=(q.moq or 0) if q else 0,
                            fixed_costs=float(q.sample_cost or 0.0) if q else 0.0, currency=ccy),
        assumptions=assumptions or _plan_anchored_assumptions(tp.production_quantity, _run_sizes(run)),
        planned_quantity=tp.production_quantity,
    )
