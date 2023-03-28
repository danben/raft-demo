import aiofiles
import asyncio
import json
import os

from aiofiles.threadpool.text import AsyncTextIOWrapper
from dataclasses import dataclass, field
from typing import Self

from raft_pb2 import AppendEntriesRequest, LogEntry
from task_scheduler import run_in_background


@dataclass(slots=True)
class Log:
    _path: str = field()
    _commit_index: int = field(default=-1)
    _last_applied: int = field(default=-1)
    _fp: AsyncTextIOWrapper = field(init=False)
    _entries: list[LogEntry] = field(default_factory=list)
    _cur_state: dict[str, str] = field(default_factory=dict)
    _apply_entries_task: asyncio.Task | None = field(default=None)

    def __del__(self: Self) -> None:
        run_in_background(self._fp.close())

    def is_empty(self: Self) -> bool:
        ret = len(self._entries) == 0
        return ret

    def num_entries(self: Self) -> int:
        # TODO: redo this logic when implementing log compaction
        return len(self._entries)

    def last_index_and_term(self: Self) -> tuple[int, int]:
        last_index: int = -1
        last_term: int = -1

        if not self.is_empty():
            last_entry = self._entries[-1]
            last_index = last_entry.index
            last_term = last_entry.term

        return last_index, last_term

    def term_for_index(self: Self, index: int) -> int:
        if index < len(self._entries):
            return self._entries[index].term
        return -1

    def get_entries_from(self: Self, start_index: int) -> list[LogEntry]:
        return self._entries[start_index:]

    def get_value(self: Self, key: str) -> str | None:
        if key in self._cur_state:
            return self._cur_state[key]
        return None

    def add_new_entry(self: Self, term: int, key: str, value: str) -> None:
        index: int = self.last_index_and_term()[0] + 1
        entry: LogEntry = LogEntry(term=term, index=index, key=key,
                                   value=value)
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

    def can_append_entries(self: Self,
                           append_entries_request:
                           AppendEntriesRequest) -> bool:
        prev_log_index = append_entries_request.prev_log_index
        if prev_log_index == -1:
            return True

        if prev_log_index < len(self._entries):
            return self._entries[prev_log_index].term == \
                    append_entries_request.prev_log_term
        return False

    async def _apply_entry(self: Self, entry: LogEntry) -> None:
        self._cur_state[entry.key] = entry.value
        json_entry = json.dumps({'key': entry.key, 'value': entry.value})
        await self._fp.write(f'{json_entry}\n')

    async def _maybe_apply_entries(self: Self) -> None:
        # Consider an entry applied once we've synchronized it to disk
        applied: int = 0
        while self._last_applied < self._commit_index:
            await self._apply_entry(self._entries[self._last_applied+1])
            applied += 1

        await self._fp.flush()
        self._last_applied += applied

        self._apply_entries_task = None

    def commit_index(self: Self) -> int:
        return self._commit_index

    def set_commit_index(self: Self, new_commit_index: int) -> None:
        """ Update our notion of the most recent committed log entry.
        If we aren't already, start a task in the background to apply
        any new entries to the state machine.
        """
        self._commit_index = new_commit_index
        if self._apply_entries_task is None:
            self._apply_entries_task = \
                asyncio.create_task(self._maybe_apply_entries())

    @classmethod
    async def create(cls, path: str) -> Self:
        ret = cls(path)
        file_exists: bool = os.path.isfile(path)
        if file_exists:
            ret._fp = await aiofiles.open(ret._path, 'r+')
            lines = await ret._fp.readlines()
            for line in lines:
                d = json.loads(line)
                key: str = d['key']
                value: str = d['value']
                e = LogEntry(key=key, value=value)
                ret._entries.append(e)
                ret._cur_state[key] = value
        else:
            ret._fp = await aiofiles.open(ret._path, 'w+')
        return ret
