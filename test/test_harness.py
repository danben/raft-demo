import asyncio
import multiprocessing
import os
import time
import uvloop

from multiprocessing import Process

from cluster_client import Client
from raft_node import Config, Node


NUM_NODES: int = 5
START_PORT: int = 12345
HEARTBEAT_TIMEOUT_MS: int = 1000
MIN_ELECTION_TIMEOUT_MS: int = 200
MAX_ELECTION_TIMEOUT_MS: int = 400
APPEND_ENTRIES_TIMEOUT_MS: int = 1000
RUN_DIR = "/tmp"


class Harness:
    @staticmethod
    def log_file_path(raft_server_port: int) -> str:
        return f"{RUN_DIR}/{raft_server_port}-log.txt"

    @staticmethod
    def persistent_state_file_path(raft_server_port: int) -> str:
        return f"{RUN_DIR}/{raft_server_port}-state.txt"

    @staticmethod
    def make_config(
        all_raft_server_ports: list[int],
        raft_server_port: int,
        cluster_server_port: int,
    ) -> Config:
        return Config(
            raft_server_port=raft_server_port,
            cluster_server_port=cluster_server_port,
            all_raft_server_ports=all_raft_server_ports,
            heartbeat_timeout_ms=HEARTBEAT_TIMEOUT_MS,
            min_election_timeout_ms=MIN_ELECTION_TIMEOUT_MS,
            max_election_timeout_ms=MAX_ELECTION_TIMEOUT_MS,
            append_entries_timeout_ms=APPEND_ENTRIES_TIMEOUT_MS,
            log_file=Harness.log_file_path(raft_server_port),
            persistent_state_file=Harness.persistent_state_file_path(
                raft_server_port
            ),
        )

    @staticmethod
    def start_node(
        all_raft_server_ports: list[int],
        raft_server_port: int,
        cluster_server_port: int,
    ) -> None:
        config: Config = Harness.make_config(
            all_raft_server_ports,
            raft_server_port=raft_server_port,
            cluster_server_port=cluster_server_port,
        )
        node: Node = Node(config)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(node.startup())

    @staticmethod
    def start_nodes(all_ports) -> dict[int, Process]:
        args_list: list[tuple[list[int], int, int]] = [
            (all_ports, port, port + NUM_NODES) for port in all_ports
        ]
        ps = {
            args[1]: Process(target=Harness.start_node, args=args)
            for args in args_list
        }
        for p in ps.values():
            p.start()
        return ps

    @staticmethod
    def run_test(test, remove_files=True):
        all_ports = list(range(START_PORT, START_PORT + NUM_NODES))
        ps = Harness.start_nodes(all_ports)
        # Wait for raft nodes to come up
        time.sleep(2)
        cluster_client = Client(all_ports)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(test(cluster_client, ps))
        for p in ps.values():
            p.kill()
        if remove_files:
            for port in all_ports:
                log_file = Harness.log_file_path(port)
                persistent_state_file = Harness.persistent_state_file_path(
                    port
                )

                if os.path.isfile(log_file):
                    os.remove(log_file)

                if os.path.isfile(persistent_state_file):
                    os.remove(persistent_state_file)


async def test_basic(
    cluster_client: Client, node_processes: dict[int, Process]
) -> None:
    await cluster_client.propose_mapping("TB_key", "TB_value")
    v = await cluster_client.get_value("TB_key")
    print(f"Cluster says value for TB_key is {v}")


async def test_leader_dies(
    cluster_client: Client, node_processes: dict[int, Process]
) -> None:
    # Wait for an election to finish
    await asyncio.sleep(2)

    # Propose a mapping in order to cache the current leader
    await cluster_client.propose_mapping("TLD_key_1", "TLD_value_1")

    await asyncio.sleep(2)
    # Kill the current leader
    leader_id = cluster_client.current_leader
    assert leader_id is not None
    leader_process = node_processes[leader_id]
    print(f"Test: killing the leader ({leader_id})")
    leader_process.kill()

    # Wait for an election to finish
    await asyncio.sleep(2)

    # Propose a new mapping
    await cluster_client.propose_mapping("TLD_key_2", "TLD_value_2")

    # Wait for it to replicate
    await asyncio.sleep(2)

    print(f"Test: bringing up node {leader_id} (previously killed leader)")
    # Bring up the old leader
    p = Process(
        target=Harness.start_node,
        args=(
            cluster_client.all_raft_server_ports(),
            leader_id,
            leader_id + NUM_NODES,
        ),
    )
    node_processes[leader_id] = p
    p.start()

    # Wait for replication on the new leader
    await asyncio.sleep(2)


if __name__ == "__main__":
    uvloop.install()
    multiprocessing.set_start_method("spawn")
    Harness.run_test(test_leader_dies, remove_files=False)
