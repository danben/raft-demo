from dataclasses import dataclass, field, InitVar
from typing import Any, Callable, Coroutine, Self

import grpc

from rpc.raft_pb2_grpc import ClusterServicer, add_ClusterServicer_to_server
from rpc.raft_pb2 import GetValueResponse, Key, Mapping, ProposeMappingResponse


@dataclass(kw_only=True)
class Servicer(ClusterServicer):
    get_value_handler: Callable[[Key], GetValueResponse]
    propose_mapping_handler: Callable[
        [Mapping], Coroutine[Any, Any, ProposeMappingResponse]
    ]

    async def GetValue(
        self, request: Key, context: grpc.aio.ServicerContext
    ) -> GetValueResponse:
        return self.get_value_handler(request)

    async def ProposeMapping(
        self, request: Mapping, context: grpc.aio.ServicerContext
    ) -> ProposeMappingResponse:
        return await self.propose_mapping_handler(request)


@dataclass(slots=True, kw_only=True)
class Server:
    port: int
    server: grpc.aio.Server = field(default_factory=grpc.aio.server)
    servicer: InitVar[Servicer]

    def __post_init__(self: Self, servicer: Servicer) -> None:
        add_ClusterServicer_to_server(servicer, self.server)
        self.server.add_insecure_port(f"[::]:{self.port}")

    async def serve(self: Self) -> None:
        await self.server.start()

    async def wait_for_termination(self: Self) -> None:
        await self.server.wait_for_termination()
