import asyncio
from abc import ABC, abstractmethod
from dataclasses import InitVar, dataclass, field


class NodeState(ABC):
    @abstractmethod
    def teardown(self):
        pass


@dataclass(slots=True)
class LeaderState(NodeState):
    all_ports: InitVar[list[int]]
    my_port: InitVar[int]
    last_log_index: InitVar[int]

    # Filling in this future allows us to cancel the heartbeat loop.
    # We do this when we receive an RPC request with a term higher
    # than our own.
    heartbeat_loop_done: asyncio.Future | None = field(default=None)

    # This dict is only populated when we're in the middle of sending
    # AppendEntries rpcs to the other nodes. We store it here so we
    # can cancel any outstanding tasks if we need to transition out of
    # leader status.
    append_entries_tasks: dict[int, asyncio.Task] = field(default_factory=dict)

    # next_index starts as last log index + 1. This is
    # the next index to send to the given server. It adjusts
    # as append_entries RPCs succeed or fail.
    next_index: dict[int, int] = field(default_factory=dict)

    # match index starts as 0 and is updated as followers
    # confirm their highest replication indices.
    match_index: dict[int, int] = field(default_factory=dict)

    def __post_init__(
        self, all_ports: list[int], my_port: int, last_log_index: int
    ) -> None:
        for port in all_ports:
            if port != my_port:
                self.next_index[port] = last_log_index + 1
                self.match_index[port] = 0

    def teardown(self):
        if self.heartbeat_loop_done is not None:
            self.heartbeat_loop_done.cancel()

        for task in self.append_entries_tasks.values():
            task.cancel()


@dataclass(slots=True)
class CandidateState(NodeState):
    election_task: asyncio.Task | None = field(default=None)

    def teardown(self):
        if self.election_task is not None:
            self.election_task.cancel()
            self.election_task = None


@dataclass(slots=True)
class FollowerState(NodeState):
    leader: int | None = field(default=None)
    receive_heartbeats_task: asyncio.Task | None = field(default=None)

    def teardown(self):
        if self.receive_heartbeats_task is not None:
            self.receive_heartbeats_task.cancel()
