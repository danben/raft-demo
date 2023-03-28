import asyncio

from multiprocessing import Process

from cluster_client import Client
from raft_node import Config, Node


NUM_NODES: int = 5
START_PORT: int = 12345
HEARTBEAT_TIMEOUT_MS: int = 1000
MIN_ELECTION_TIMEOUT_MS: int = 200
MAX_ELECTION_TIMEOUT_MS: int = 400
APPEND_ENTRIES_TIMEOUT_MS: int = 1000
RUN_DIR = '/tmp'


def make_config(all_raft_server_ports: list[int], raft_server_port: int,
                cluster_server_port: int) -> Config:
    return Config(raft_server_port=raft_server_port,
                  cluster_server_port=cluster_server_port,
                  all_raft_server_ports=all_raft_server_ports,
                  heartbeat_timeout_ms=HEARTBEAT_TIMEOUT_MS,
                  min_election_timeout_ms=MIN_ELECTION_TIMEOUT_MS,
                  max_election_timeout_ms=MAX_ELECTION_TIMEOUT_MS,
                  append_entries_timeout_ms=APPEND_ENTRIES_TIMEOUT_MS,
                  log_file=f'{RUN_DIR}/{raft_server_port}-log.txt',
                  persistent_state_file=f'{RUN_DIR}/'
                                        f'{raft_server_port}-state.txt')


def start_node(all_raft_server_ports: list[int], raft_server_port: int,
               cluster_server_port: int) -> None:
    node: Node = Node(make_config(all_raft_server_ports,
                                  raft_server_port=raft_server_port,
                                  cluster_server_port=cluster_server_port))
    loop = asyncio.get_event_loop()
    loop.run_until_complete(node.startup())


def start_nodes(all_ports) -> list[Process]:
    args_list: list[tuple[list[int], int, int]] = \
        [(all_ports, port, port+NUM_NODES) for port in all_ports]
    ps = [Process(target=start_node, args=args) for args in args_list]
    for p in ps:
        p.start()
    return ps


async def run_test(ps: list[Process]) -> None:
    # Wait for raft nodes to come up
    await asyncio.sleep(2)
    cluster_client = Client([port+NUM_NODES for port in all_ports])
    await cluster_client.propose_mapping("key", "value")
    v = await cluster_client.get_value("key")
    print(f'Cluster says value for key is {v}')
    for p in ps:
        p.join()


if __name__ == '__main__':
    all_ports = list(range(START_PORT, START_PORT+NUM_NODES))
    ps = start_nodes(all_ports)
    asyncio.run(run_test(ps))
