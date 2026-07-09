from dataclasses import dataclass, field
from typing import Generic, TypeVar

ItemT = TypeVar("ItemT")


@dataclass(frozen=True, slots=True)
class ProviderPullStepResult(Generic[ItemT]):
    count_key: str
    items: list[ItemT] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    provider_failed: bool = False
    malformed_payload: bool = False

    @property
    def count(self) -> int:
        return len(self.items)


@dataclass(slots=True)
class ProviderPullCollector(Generic[ItemT]):
    all_provider_failure_error: str
    all_malformed_payload_error: str
    step_count: int
    items: list[ItemT] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    provider_failures: int = 0
    malformed_payloads: int = 0

    def add_result(self, result: ProviderPullStepResult[ItemT]) -> None:
        self.items.extend(result.items)
        self.warnings.extend(result.warnings)

        if result.provider_failed:
            self.provider_failures += 1
        if result.malformed_payload:
            self.malformed_payloads += 1

    def raise_for_unusable_result(self) -> None:
        if self.provider_failures == self.step_count:
            raise ValueError(self.all_provider_failure_error)
        if self.malformed_payloads == self.step_count:
            raise ValueError(self.all_malformed_payload_error)
