from dataclasses import dataclass, field
from typing import Self

import grpc
import raft_pb2_grpc

from raft_pb2 import AppendEntriesRequest, AppendEntriesResponse, LogEntry
from raft_pb2 import RequestVoteResponse, VoteRequest


@dataclass
class Client:
    port: int
    channel: grpc.aio.Channel = field(init=False)
    stub: raft_pb2_grpc.RaftStub = field(init=False)

    def __post_init__(self) -> None:
        self.channel = grpc.aio.insecure_channel(f'localhost:{self.port}')
        self.stub = raft_pb2_grpc.RaftStub(self.channel)

    async def close(self: Self) -> None:
        await self.channel.close()

    async def append_entries(
            self: Self, term: int, leader_id: int, prev_log_index: int,
            prev_log_term: int, leader_commit: int,
            log_entries: list[LogEntry]) -> AppendEntriesResponse:
        return await self.stub.AppendEntries(
                AppendEntriesRequest(
                    term=term, requester_id=leader_id,
                    prev_log_index=prev_log_index,
                    prev_log_term=prev_log_term,
                    leader_commit=leader_commit,
                    log_entries=log_entries))

    async def request_vote(
            self: Self, term: int, candidate_id: int,
            last_log_index: int, last_log_term: int) -> RequestVoteResponse:
        return await self.stub.RequestVote(
                VoteRequest(
                    term=term, requester_id=candidate_id,
                    last_log_index=last_log_index,
                    last_log_term=last_log_term))
