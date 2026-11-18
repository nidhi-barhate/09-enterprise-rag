"""Check search quality against the seeded incidents.

Each question has a known right answer (a scenario). For every question we look at
the top results and ask: was the first one from the right scenario, and how many
of the top 5 were?

Run from the project root (after seeding):
    python -m app.scripts.evaluate_search
"""

from dataclasses import dataclass

from app.config.connection import SessionLocal
from app.config.qdrant import get_qdrant_client
from app.repository.incident_repository import IncidentRepository
from app.scripts.seed_data import scenario_of
from app.services.embedding_service import get_embedding_service
from app.services.incident_search_service import IncidentSearchService

# Written in different words than the seeded titles on purpose.
QUESTIONS = [
    ("payments are timing out after we deployed, all the db connections are taken", "db-pool"),
    ("checkout is broken, the app cannot get a connection to the database", "db-pool"),
    ("no free space left on the server", "disk-full"),
    ("the partition is full and jobs cannot write files", "disk-full"),
    ("users get a certificate warning in the browser", "tls-cert"),
    ("our ssl certificate has expired", "tls-cert"),
    ("redis is down and the whole site is slow", "cache-down"),
    ("user sessions keep getting lost", "cache-down"),
    ("the container keeps getting killed for using too much memory", "oom"),
    ("a memory leak keeps crashing the service", "oom"),
    ("errors started immediately after the new version went live", "deploy-regression"),
    ("we need to roll back a bad release", "deploy-regression"),
    ("services cannot resolve each other's hostnames", "dns"),
    ("name lookups are failing intermittently", "dns"),
    ("the queue is backed up and messages are delayed", "queue-backlog"),
    ("kafka consumers are lagging behind", "queue-backlog"),
    ("a vendor api is rate limiting our requests", "upstream"),
    ("the third party provider is down so payments fail", "upstream"),
    ("a database query is scanning the whole table and cpu is maxed out", "slow-query"),
    ("reports take forever now that the table has grown", "slow-query"),
]


@dataclass
class QuestionResult:
    question: str
    expected: str
    top1: str
    precision: float  # share of the top-k results that came from the expected scenario


@dataclass
class EvaluationResult:
    rows: list[QuestionResult]

    @property
    def top1_accuracy(self) -> float:
        return sum(r.top1 == r.expected for r in self.rows) / len(self.rows)

    @property
    def mean_precision(self) -> float:
        return sum(r.precision for r in self.rows) / len(self.rows)


def evaluate(search, questions=QUESTIONS, k: int = 5) -> EvaluationResult:
    rows = []
    for question, expected in questions:
        scenarios = [scenario_of(h.incident.tags) for h in search.search(question, limit=k)]
        rows.append(
            QuestionResult(
                question=question,
                expected=expected,
                top1=scenarios[0] if scenarios else "(none)",
                precision=(scenarios.count(expected) / k) if scenarios else 0.0,
            )
        )
    return EvaluationResult(rows)


def main() -> None:
    with SessionLocal() as session:
        search = IncidentSearchService(
            get_qdrant_client(), get_embedding_service(), IncidentRepository(session)
        )
        result = evaluate(search)

    print(f"{'question':68} {'expected':18} {'top result':18} {'top-5 right'}")
    for r in result.rows:
        mark = "ok " if r.top1 == r.expected else "MISS"
        print(f"{r.question[:66]:68} {r.expected:18} {r.top1:18} {r.precision * 5:.0f}/5  {mark}")
    print()
    print(f"First result from the right scenario: {result.top1_accuracy:.0%}")
    print(f"Average share of top 5 from the right scenario: {result.mean_precision:.0%}")


if __name__ == "__main__":
    main()
