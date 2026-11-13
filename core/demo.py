"""Backward-compatible entry point for the JSON sample dataset."""
from core.database import Database
from core.dataset_loader import load_sample_dataset


def load_demo(db: Database) -> int:
    """Load missing sample cases; retain the existing public function name."""
    return load_sample_dataset(db)
