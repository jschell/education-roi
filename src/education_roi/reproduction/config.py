from dataclasses import asdict, dataclass
from hashlib import sha256
from json import dumps


@dataclass(frozen=True)
class ZhangConfiguration:
    acs_vintages: tuple[int, ...]
    minimum_age: int
    maximum_age: int
    target_dollar_year: int
    college_ages: tuple[int, ...]
    books_and_supplies: float
    student_earnings: float
    nontuition_attribution: float
    selection_adjustment: float
    selection_earnings_premium: float
    discount_rate: float

    def __post_init__(self) -> None:
        if not self.acs_vintages or tuple(sorted(set(self.acs_vintages))) != self.acs_vintages:
            raise ValueError("ACS vintages must be unique and ordered")
        if self.minimum_age > self.maximum_age:
            raise ValueError("minimum_age cannot exceed maximum_age")
        expected_ages = (
            tuple(range(self.college_ages[0], self.college_ages[-1] + 1))
            if self.college_ages
            else ()
        )
        if not self.college_ages or expected_ages != self.college_ages:
            raise ValueError("college ages must be ordered and consecutive")
        if not 0 <= self.nontuition_attribution <= 1 or not 0 <= self.selection_adjustment <= 1:
            raise ValueError("attribution and selection assumptions must be between 0 and 1")
        if (
            min(
                self.books_and_supplies,
                self.student_earnings,
                self.selection_earnings_premium,
                self.discount_rate,
            )
            < 0
        ):
            raise ValueError("monetary and rate assumptions cannot be negative")

    def as_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["acs_vintages"] = list(self.acs_vintages)
        value["college_ages"] = list(self.college_ages)
        return value

    @property
    def configuration_hash(self) -> str:
        return sha256(
            dumps(self.as_dict(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


def published_zhang_configuration() -> ZhangConfiguration:
    return ZhangConfiguration(
        tuple(range(2009, 2022)),
        18,
        65,
        2021,
        (18, 19, 20, 21),
        1_000,
        3_268,
        0.50,
        0.25,
        0.60,
        0.04,
    )
