from dataclasses import dataclass


TEHRAN_TOTAL_INDEX_CODE = "32097828799138957"


@dataclass(frozen=True)
class BenchmarkConfig:
    code: str
    name: str


TEHRAN_TOTAL_INDEX = BenchmarkConfig(
    code=TEHRAN_TOTAL_INDEX_CODE,
    name="شاخص کل",
)
