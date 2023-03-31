from dataclasses import dataclass, field
from typing import Callable, Self

import grpc
import raft_pb2_grpc

from raft_pb2 import (
    AppendEntriesRequest,
    AppendEntriesResponse,
    RequestVoteResponse,
    VoteRequest,
)


@dataclass(kw_only=True)
class Servicer(raft_pb2_grpc.RaftServicer):
    request_vote_handler: Callable[[VoteRequest], RequestVoteResponse]
    append_entries_handler: Callable[
        [AppendEntriesRequest], AppendEntriesResponse
    ]

    async def RequestVote(
        self, request: VoteRequest, context: grpc.aio.ServicerContext
    ) -> RequestVoteResponse:
        return self.request_vote_handler(request)

    async def AppendEntries(
        self, request: AppendEntriesRequest, context: grpc.aio.ServicerContext
    ) -> AppendEntriesResponse:
        return self.append_entries_handler(request)


@dataclass(slots=True, kw_only=True)
class Server:
    port: int
    request_vote_handler: Callable[[VoteRequest], RequestVoteResponse]
    append_entries_handler: Callable[
        [AppendEntriesRequest], AppendEntriesResponse
    ]
    server: grpc.aio.Server = field(default_factory=grpc.aio.server)

    def __post_init__(self: Self) -> None:
        servicer: Servicer = Servicer(
            request_vote_handler=self.request_vote_handler,
            append_entries_handler=self.append_entries_handler,
        )
        raft_pb2_grpc.add_RaftServicer_to_server(servicer, self.server)
        self.server.add_insecure_port(f"[::]:{self.port}")

    async def serve(self: Self) -> None:
        await self.server.start()

    async def wait_for_termination(self: Self) -> None:
        await self.server.wait_for_termination()
