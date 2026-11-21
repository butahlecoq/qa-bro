"""Apply retention limits to a local QA Bro database."""

import argparse
import json
from pathlib import Path
from time import time_ns

from qabro.artifacts import ArtifactStore
from qabro.journal import Journal


def prune_database(database: Path, *, before_ns: int, journal_bytes: int, artifact_bytes: int) -> dict:
    if min(journal_bytes, artifact_bytes) < 0:
        raise ValueError("Retention limits must be nonnegative")
    if not database.is_file():
        raise ValueError("Expected an existing QA Bro database")
    journal = Journal(database)
    artifacts = ArtifactStore(database)
    journal_remaining = journal.prune(before_ns=before_ns, max_payload_bytes=journal_bytes)
    artifact_remaining = artifacts.prune(before=before_ns, max_bytes=artifact_bytes)
    return {
        "journal_payload_bytes": journal_remaining,
        "artifact_payload_bytes": artifact_remaining,
        "within_limits": journal_remaining <= journal_bytes and artifact_remaining <= artifact_bytes,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("--age-days", type=int, required=True)
    parser.add_argument("--journal-bytes", type=int, required=True)
    parser.add_argument("--artifact-bytes", type=int, required=True)
    args = parser.parse_args()
    if min(args.age_days, args.journal_bytes, args.artifact_bytes) < 0:
        parser.error("Age and byte limits must be nonnegative")
    print(json.dumps(prune_database(
        args.database,
        before_ns=time_ns() - args.age_days * 86_400_000_000_000,
        journal_bytes=args.journal_bytes,
        artifact_bytes=args.artifact_bytes,
    ), indent=2))
