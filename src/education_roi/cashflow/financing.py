"""Deterministic loan amortization with financing costs kept explicit."""

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class LoanTerms:
    """Fixed-rate loan assumptions from disbursement through repayment."""

    name: str
    amount_borrowed: float
    annual_interest_rate: float
    repayment_years: int
    origination_fee_rate: float = 0.0
    enrollment_years: int = 0
    grace_months: int = 0
    subsidized_during_enrollment: bool = False
    payments_per_year: int = 12

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("loan name cannot be empty")
        numeric = (self.amount_borrowed, self.annual_interest_rate, self.origination_fee_rate)
        if not all(isfinite(value) for value in numeric):
            raise ValueError("loan amounts and rates must be finite")
        if self.amount_borrowed < 0:
            raise ValueError("amount_borrowed cannot be negative")
        if self.annual_interest_rate < 0:
            raise ValueError("annual_interest_rate cannot be negative")
        if not 0 <= self.origination_fee_rate < 1:
            raise ValueError("origination_fee_rate must be between 0 and 1")
        if self.repayment_years <= 0:
            raise ValueError("repayment_years must be positive")
        if self.enrollment_years < 0 or self.grace_months < 0:
            raise ValueError("enrollment and grace periods cannot be negative")
        if self.payments_per_year <= 0:
            raise ValueError("payments_per_year must be positive")

    @property
    def origination_fee(self) -> float:
        """Fee charged on the face value of the loan."""
        return self.amount_borrowed * self.origination_fee_rate

    @property
    def net_proceeds(self) -> float:
        """Amount available after a fee is withheld from disbursement."""
        return self.amount_borrowed - self.origination_fee

    def as_dict(self) -> dict[str, str | int | float | bool]:
        """Return JSON-compatible assumptions for reproduction."""
        return {
            "name": self.name,
            "amount_borrowed": self.amount_borrowed,
            "annual_interest_rate": self.annual_interest_rate,
            "repayment_years": self.repayment_years,
            "origination_fee_rate": self.origination_fee_rate,
            "enrollment_years": self.enrollment_years,
            "grace_months": self.grace_months,
            "subsidized_during_enrollment": self.subsidized_during_enrollment,
            "payments_per_year": self.payments_per_year,
        }


@dataclass(frozen=True)
class AnnualDebtPayment:
    """Aggregated payments and balance movement for one repayment year."""

    repayment_year: int
    payment: float
    principal: float
    interest: float
    ending_balance: float


@dataclass(frozen=True)
class LoanSchedule:
    """Complete loan result, including economic financing costs."""

    terms: LoanTerms
    balance_at_repayment: float
    periodic_payment: float
    annual_payments: tuple[AnnualDebtPayment, ...]

    @property
    def total_payments(self) -> float:
        return sum(year.payment for year in self.annual_payments)

    @property
    def total_interest(self) -> float:
        """Interest accrued before and during repayment."""
        return self.total_payments - self.terms.amount_borrowed

    @property
    def total_financing_cost(self) -> float:
        """Interest plus origination fees, excluding borrowed principal."""
        return self.total_interest + self.terms.origination_fee

    def financing_costs_by_year(self) -> tuple[float, ...]:
        """Return interest-only repayment costs; principal remains education cost."""
        return tuple(year.interest for year in self.annual_payments)


def _balance_at_repayment(terms: LoanTerms) -> float:
    if terms.amount_borrowed == 0 or terms.subsidized_during_enrollment:
        return terms.amount_borrowed
    periodic_rate = terms.annual_interest_rate / terms.payments_per_year
    deferred_periods = terms.enrollment_years * terms.payments_per_year + terms.grace_months
    return terms.amount_borrowed * (1 + periodic_rate) ** deferred_periods


def build_loan_schedule(terms: LoanTerms) -> LoanSchedule:
    """Build a fixed-payment amortization schedule with monthly internal precision."""
    balance = _balance_at_repayment(terms)
    periods = terms.repayment_years * terms.payments_per_year
    periodic_rate = terms.annual_interest_rate / terms.payments_per_year
    if balance == 0:
        payment = 0.0
    elif periodic_rate == 0:
        payment = balance / periods
    else:
        payment = balance * periodic_rate / (1 - (1 + periodic_rate) ** -periods)

    annual: list[AnnualDebtPayment] = []
    for year in range(1, terms.repayment_years + 1):
        annual_payment = 0.0
        annual_principal = 0.0
        annual_interest = 0.0
        for _ in range(terms.payments_per_year):
            interest = balance * periodic_rate
            actual_payment = min(payment, balance + interest)
            principal = actual_payment - interest
            balance = max(0.0, balance - principal)
            annual_payment += actual_payment
            annual_principal += principal
            annual_interest += interest
        annual.append(
            AnnualDebtPayment(
                repayment_year=year,
                payment=annual_payment,
                principal=annual_principal,
                interest=annual_interest,
                ending_balance=balance,
            )
        )
    return LoanSchedule(terms, _balance_at_repayment(terms), payment, tuple(annual))
