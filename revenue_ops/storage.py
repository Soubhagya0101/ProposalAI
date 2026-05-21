from __future__ import annotations

import csv
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generic, Iterable, Protocol, TypeVar

from .models import Event, Feedback, Lead, Message, Metric, Record


T = TypeVar("T", bound=Record)


class Table(Protocol[T]):
    def all(self) -> list[T]:
        ...

    def append(self, record: T) -> T:
        ...

    def upsert(self, record: T) -> T:
        ...


class CsvTable(Generic[T]):
    def __init__(self, path: Path, model: type[T]) -> None:
        self.path = path
        self.model = model
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write([])

    def all(self) -> list[T]:
        with _file_lock(self.path):
            return self._read_unlocked()

    def append(self, record: T) -> T:
        with _file_lock(self.path):
            records = self._read_unlocked()
            records.append(record)
            self._write_unlocked(records)
        return record

    def upsert(self, record: T) -> T:
        with _file_lock(self.path):
            records = self._read_unlocked()
            replaced = False
            for index, existing in enumerate(records):
                if existing.id == record.id:
                    records[index] = record
                    replaced = True
                    break
            if not replaced:
                records.append(record)
            self._write_unlocked(records)
        return record

    def _write(self, records: Iterable[T]) -> None:
        with _file_lock(self.path):
            self._write_unlocked(records)

    def _read_unlocked(self) -> list[T]:
        with self.path.open("r", newline="", encoding="utf-8") as handle:
            return [self.model.from_dict(row) for row in csv.DictReader(handle)]

    def _write_unlocked(self, records: Iterable[T]) -> None:
        with self.path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.model.fieldnames())
            writer.writeheader()
            for record in records:
                writer.writerow(record.to_dict())


@contextmanager
def _file_lock(path: Path):
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        handle.seek(0)
        if handle.read(1) == b"":
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        deadline = time.time() + 30
        locked = False
        while not locked:
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError:
                if time.time() >= deadline:
                    raise TimeoutError(f"Timed out waiting for lock: {lock_path}")
                time.sleep(0.1)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class LocalJsonReports:
    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "reports"
        self.path.mkdir(parents=True, exist_ok=True)

    def write_daily(self, report: dict) -> Path:
        date = report.get("date", "unknown")
        target = self.path / f"daily-{date}.json"
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return target


class RevenueStore:
    def __init__(self, leads: Table[Lead], messages: Table[Message], events: Table[Event], feedback: Table[Feedback], metrics: Table[Metric]) -> None:
        self.leads = leads
        self.messages = messages
        self.events = events
        self.feedback = feedback
        self.metrics = metrics

    @classmethod
    def local(cls, data_dir: Path) -> "RevenueStore":
        data_dir.mkdir(parents=True, exist_ok=True)
        return cls(
            leads=CsvTable(data_dir / "leads.csv", Lead),
            messages=CsvTable(data_dir / "messages.csv", Message),
            events=CsvTable(data_dir / "events.csv", Event),
            feedback=CsvTable(data_dir / "feedback.csv", Feedback),
            metrics=CsvTable(data_dir / "metrics.csv", Metric),
        )
