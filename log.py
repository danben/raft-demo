import aiofiles
import asyncio
import json
import os

from aiofiles.threadpool.text import AsyncTextIOWrapper
from enum import Enum
from dataclasses import dataclass, field
from typing import Self

from rpc.raft_pb2 import AppendEntriesRequest, LogEntry
from task_scheduler import run_in_background


class JSONCodec:
    class Field(Enum):
        KEY = "key"
        VALUE = "value"
        TERM = "term"
        INDEX = "index"

    @staticmethod
    def decode_log_entry(d: dict[str, str]) -> LogEntry:
        key: str = d[JSONCodec.Field.KEY.value]
        value: str = d[JSONCodec.Field.VALUE.value]
        term: int = int(d[JSONCodec.Field.TERM.value])
        index: int = int(d[JSONCodec.Field.INDEX.value])
        return LogEntry(term=term, index=index, key=key, value=value)

    @staticmethod
    def encode_log_entry(entry: LogEntry) -> str:
        return json.dumps(
            {
                JSONCodec.Field.INDEX.value: entry.index,
                JSONCodec.Field.TERM.value: entry.term,
                JSONCodec.Field.KEY.value: entry.key,
                JSONCodec.Field.VALUE.value: entry.value,
            }
        )


@dataclass(slots=True)
class Log:
    _path: str
    _fp: AsyncTextIOWrapper
    _last_applied: int = field(default=-1)
    _entries: list[LogEntry] = field(default_factory=list)
    _cur_state: dict[str, str] = field(default_factory=dict)
    _commit_index: int = field(default=-1)
    _apply_entries_task: asyncio.Task | None = field(default=None)

    @classmethod
    async def create(cls, path: str) -> Self:
        ret: Self
        file_exists: bool = os.path.isfile(path)
        if file_exists:
            fp = await aiofiles.open(path, "r+")
            lines: list[str] = await fp.readlines()
            entries: list[LogEntry] = []
            cur_state: dict[str, str] = {}
            for line in lines:
                entry = json.loads(
                    line, object_hook=JSONCodec.decode_log_entry
                )
                entries.append(entry)
                cur_state[entry.key] = entry.value
            last_applied = -1
            if entries:
                last_applied = entries[-1].index
            ret = cls(path, fp, last_applied, entries, cur_state)
        else:
            fp = await aiofiles.open(ret._path, "w+")
            ret = cls(path, fp)
        return ret

    def __del__(self: Self) -> None:
        run_in_background(self._fp.close())

    def is_empty(self: Self) -> bool:
        return len(self._entries) == 0

    def last_index_and_term(self: Self) -> tuple[int, int]:
        last_index: int = -1
        last_term: int = -1

        if not self.is_empty():
            last_entry: LogEntry = self._entries[-1]
            last_index = last_entry.index
            last_term = last_entry.term

        return last_index, last_term

    def term_for_index(self: Self, index: int) -> int:
        return self._entries[index].term if index < len(self._entries) else -1

    def get_entries_from(self: Self, start_index: int) -> list[LogEntry]:
        return self._entries[start_index:]

    def get_value(self: Self, key: str) -> str | None:
        if key in self._cur_state:
            return self._cur_state[key]
        return None

    def add_new_entry(self: Self, term: int, key: str, value: str) -> None:
        index: int = self.last_index_and_term()[0] + 1
        entry: LogEntry = LogEntry(
            term=term, index=index, key=key, value=value
        )
        self._entries.append(entry)

    def append_entries(self: Self, entries: list[LogEntry]) -> None:
        # Need to overwrite any entries whose indices we already have
        # entries for. Everything else can be appended.
        for entry in entries:
            # TODO: redo this logic when implementing log compaction
            if entry.index < len(self._entries):
                self._entries[entry.index] = entry
            else:
                assert entry.index == len(self._entries)
                self._entries.append(entry)

    def can_append_entries(
        self: Self, append_entries_request: AppendEntriesRequest
    ) -> bool:
        prev_log_index = append_entries_request.prev_log_index
        if prev_log_index == -1:
            return True

        if prev_log_index < len(self._entries):
            return (
                self._entries[prev_log_index].term
                == append_entries_request.prev_log_term
            )
        return False

    async def _apply_entry(self: Self, entry: LogEntry) -> None:
        self._cur_state[entry.key] = entry.value
        await self._fp.write(f"{JSONCodec.encode_log_entry(entry)}\n")

    async def _maybe_apply_entries(self: Self) -> None:
        # Consider an entry applied once we've synchronized it to disk.
        # For efficiency, attempt to batch writes.
        next_index: int = self._last_applied + 1
        while next_index <= self._commit_index:
            await self._apply_entry(self._entries[next_index])
            next_index += 1

        await self._fp.flush()
        self._last_applied = next_index - 1

        self._apply_entries_task = None

    def commit_index(self: Self) -> int:
        return self._commit_index

    def set_commit_index(self: Self, new_commit_index: int) -> None:
        """Update our notion of the most recent committed log entry.
        If we don't already have one, start a task in the background
        to apply any new entries to the state machine.
        """
        self._commit_index = new_commit_index
        if self._apply_entries_task is None:
            self._apply_entries_task = asyncio.create_task(
                self._maybe_apply_entries()
            )
