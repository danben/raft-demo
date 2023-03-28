import random

from dataclasses import dataclass, field
from typing import Self

import grpc

import raft_pb2_grpc

from grpc.aio._call import AioRpcError

from raft_pb2 import GetValueResponse, Key, Mapping
from raft_pb2 import ProposeMappingResponse


@dataclass(slots=True)
class RpcClient:
    port: int = field()
    channel: grpc.aio.Channel = field(init=False)
    stub: raft_pb2_grpc.ClusterStub = field(init=False)

    def __post_init__(self) -> None:
        self.channel = grpc.aio.insecure_channel(f'localhost:{self.port}')
        self.stub = raft_pb2_grpc.ClusterStub(self.channel)

    async def close(self: Self) -> None:
        await self.channel.close()

    async def get_value_rpc(self: Self, key: str) -> GetValueResponse:
        return await self.stub.GetValue(Key(key=key))

    async def propose_mapping_rpc(self: Self, key: str, value: str) \
            -> ProposeMappingResponse:
        return await self.stub.ProposeMapping(Mapping(key=key, value=value))


@dataclass(slots=True)
class Client:
    _all_raft_server_ports: list[int] = field()
    _current_leader: int | None = field(default=None)
    _rpc_clients_by_port: dict[int, RpcClient] = field(default_factory=dict)

    def __post_init__(self: Self) -> None:
        self._rpc_clients_by_port = {port: RpcClient(port)
                                     for port in self._all_raft_server_ports}
        self._choose_a_random_server()

    def _choose_a_random_server(self: Self) -> None:
        self._current_leader = \
            self._all_raft_server_ports[
                random.randrange(len(self._all_raft_server_ports))]

    def _print(self: Self, msg: str) -> None:
        print(f'Client: {msg}')

    async def get_value(self: Self, key: str) -> str:
        if self._current_leader is None:
            self._choose_a_random_server()

        assert self._current_leader is not None
        rpc_client: RpcClient = self._rpc_clients_by_port[self._current_leader]
        resp = await rpc_client.get_value_rpc(key)
        return resp.value

    async def propose_mapping(self: Self, key: str, value: str) -> None:
        success: bool = False
        while not success:
            if self._current_leader is None:
                self._choose_a_random_server()

            assert self._current_leader is not None
            rpc_client: RpcClient = \
                self._rpc_clients_by_port[self._current_leader]
            try:
                resp: ProposeMappingResponse = \
                    await rpc_client.propose_mapping_rpc(key, value)
                success = resp.success
                self._current_leader = \
                    resp.current_leader + len(self._all_raft_server_ports) \
                    if resp.current_leader is not None \
                    else None

                self._print(f'New leader is {resp.current_leader}')
            except AioRpcError:
                self._print('Unable to connect; trying a different server')
                self._choose_a_random_server()
