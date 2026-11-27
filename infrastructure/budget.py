"""Pure admission preflight; NOT an atomic billing ledger or runtime integration."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Admission:
    enabled: bool = False
    monthly_limit: int = 0
    job_limit: int = 0
    concurrency_limit: int = 0

    def allows(self, *, estimate: int, spent: int, reserved: int, active: int) -> bool:
        values = (estimate, spent, reserved, active, self.monthly_limit,
                  self.job_limit, self.concurrency_limit)
        if any(type(value) is not int or value < 0 for value in values):
            return False
        return (self.enabled is True and 0 < estimate <= self.job_limit
                and spent + reserved + estimate <= self.monthly_limit
                and active < self.concurrency_limit)
