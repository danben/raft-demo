import aiofiles
import asyncio
import json
import os
import random
import sys

from asyncio.exceptions import CancelledError, TimeoutError
from collections.abc import Coroutine, Iterable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Callable, Self, TypeVar

import cluster_server
import raft_server

from log import Log
from node_state import CandidateState, FollowerState, LeaderState, NodeState
from raft_client import Client
from raft_pb2 import AppendEntriesRequest, AppendEntriesResponse
from raft_pb2 import GetValueResponse, LogEntry, Key, Mapping
from raft_pb2 import ProposeMappingResponse, RequestVoteResponse, VoteRequest
from task_scheduler import run_in_background, run_every


@dataclass(slots=True, frozen=True)
class Config:
    raft_server_port: int
    cluster_server_port: int
    all_raft_server_ports: list[int]
    heartbeat_timeout_ms: int
    min_election_timeout_ms: int
    max_election_timeout_ms: int
    append_entries_timeout_ms: int
    log_file: str
    persistent_state_file: str


Req = TypeVar("Req", AppendEntriesRequest, VoteRequest)
Nd = TypeVar("Nd", bound='Node')
Rsp = TypeVar("Rsp")


def check_term(f: Callable[[Nd, Req], Rsp]) -> Callable[[Nd, Req], Rsp]:
    """ Decorator to wrap RPC request handlers with common
    functionality. Specifically, this handles the following:
      - when we see an RPC from a new leader, update our known leader
      - record a heartbeat on every RPC from the current leader
    """
    def wrapper(self: Nd, rpc_request: Req) -> Rsp:
        term = rpc_request.term

        # If there is a term change, update and possibly change state
        if term > self._current_term:
            self._print(f'New term {term}. Becoming follower')
            self._current_term = term
            self._voted_for = None
            run_in_background(self._update_persistent_state())
            self._become_follower(rpc_request.requester_id)
        elif term == self._current_term \
                and isinstance(self._state, FollowerState) \
                and isinstance(rpc_request, AppendEntriesRequest) \
                and self._state.leader == rpc_request.requester_id:
            # Reset the heartbeat timer
            run_in_background(self._wait_for_next_heartbeat())

        return f(self, rpc_request)

    return wrapper


@dataclass(slots=True)
class Node:
    config: Config
    _state: NodeState = field(default_factory=FollowerState)
    _current_term: int = field(init=False)
    _voted_for: int | None = field(init=False)
    _log: Log = field(init=False)
    _raft_rpc_server: raft_server.Server = field(init=False)
    _cluster_rpc_server: cluster_server.Server = field(init=False)
    _raft_rpc_clients: dict[int, Client] = field(init=False)

    def __post_init__(self: Self) -> None:
        self._raft_rpc_server = \
            raft_server.Server(
                port=self.config.raft_server_port,
                request_vote_handler=self._request_vote_handler,
                append_entries_handler=self._append_entries_handler)

        self._cluster_rpc_server = \
            cluster_server.Server(
                port=self.config.cluster_server_port,
                get_value_handler=self._get_value_handler,
                propose_mapping_handler=self._propose_mapping_handler)

        self._raft_rpc_clients = {
            other_port: Client(port=other_port)
            for other_port in self.config.all_raft_server_ports
            if other_port != self.config.raft_server_port
            }

    def _print(self: Self, msg: str) -> None:
        print(f'Node {self.config.raft_server_port}: {msg}')

    async def _load_persistent_state(self: Self) -> None:
        self._current_term, self._voted_for = -1, None
        if os.path.isfile(self.config.persistent_state_file):
            with open(self.config.persistent_state_file, 'r') as f:
                self._current_term, self_voted_for = json.load(f)
                self._print(f'Initialized persistent state from disk: '
                            f'term {self._current_term}, '
                            f'voted_for {self._voted_for}')
        else:
            self._print('No persistent state file. Initializing term to -1')

        self._log = await Log.create(self.config.log_file)
        self._print(f'Initial state machine: {self._log._cur_state}')

    async def _update_persistent_state(self: Self) -> None:
        async with aiofiles.open(self.config.persistent_state_file, 'w') as f:
            contents: str = json.dumps((self._current_term, self._voted_for))
            self._print(f'Writing state to disk: {contents}')
            await f.write(contents)
            await f.flush()

    @check_term
    def _request_vote_handler(self: Self, vote_request: VoteRequest) \
            -> RequestVoteResponse:
        """ We can only vote for the requesting candidate under the following
        conditions:
         - the candidate's term is at least as large as our current term
         - we have not voted for a different candidate for this term
         - the candidate's log is at least as up to date as ours
        """
        requester_id: int = vote_request.requester_id
        if vote_request.term >= self._current_term \
                and (self._voted_for is None
                     or self._voted_for == requester_id):
            last_log_index, last_log_term = self._log.last_index_and_term()
            if vote_request.last_log_index >= last_log_index \
                    and vote_request.last_log_term >= last_log_term:
                self._print(f'Voting yes for {requester_id}')
                self._voted_for = requester_id
                run_in_background(self._update_persistent_state())
                return RequestVoteResponse(term=self._current_term,
                                           vote_granted=True)

        self._print(f'Voting no for {requester_id}')
        return RequestVoteResponse(term=self._current_term, vote_granted=False)

    @check_term
    def _append_entries_handler(self: Self, append_entries_request:
                                AppendEntriesRequest) -> AppendEntriesResponse:
        """ Iff this is a viable leader (based on term) and the term for our
        entry at prevLogIndex matches the term specified in prevLogTerm,
        we can go ahead and update our log with the new entries. Additionally,
        if the leader has sent us a higher commit index than the one that we
        know, we can update our own and apply the relevant entries.
        """
        if append_entries_request.log_entries:
            self._print(f'Received {len(append_entries_request.log_entries)} '
                        'log entries from '
                        f'{append_entries_request.requester_id}')
        if append_entries_request.term >= self._current_term \
                and self._log.can_append_entries(append_entries_request):
            if append_entries_request.log_entries:
                self._print('Ok to append')
            self._log.append_entries(list(append_entries_request.log_entries))
            if append_entries_request.leader_commit > self._log.commit_index():
                new_commit_index = append_entries_request.leader_commit
                if append_entries_request.log_entries:
                    new_commit_index = \
                        min(new_commit_index,
                            append_entries_request.log_entries[-1].index)
                self._print('Got new commit index from leader: '
                            f'{new_commit_index}')
                self._log.set_commit_index(new_commit_index)
            return AppendEntriesResponse(term=self._current_term, success=True)

        if append_entries_request.log_entries:
            self._print('Rejecting')
        return AppendEntriesResponse(term=self._current_term, success=False)

    def _get_value_handler(self: Self, key: Key) -> GetValueResponse:
        return GetValueResponse(key=key.key,
                                value=self._log.get_value(key.key))

    async def _append_entries_on_one_server(self: Self, server: int) -> int:
        """ Attempt to replicate as much as we can on the given server.
        If the request times out, try again. If it fails, that means that
        the server disagrees with prev_log_index and prev_log_term. In that
        case, decrement next_index and try again.
        """
        assert isinstance(self._state, LeaderState)

        timeout: int = int(self.config.append_entries_timeout_ms / 1000)
        while True:
            # Refresh these on each iteration, in case new entries came in
            # since the last one
            next_index_for_this_server: int = self._state.next_index[server]
            entries_to_send: list[LogEntry] = \
                self._log.get_entries_from(next_index_for_this_server)

            try:
                async with asyncio.timeout(timeout):
                    resp: AppendEntriesResponse = await \
                        self._raft_rpc_clients[server].append_entries(
                            term=self._current_term,
                            leader_id=self.config.raft_server_port,
                            prev_log_index=next_index_for_this_server-1,
                            prev_log_term=self._log.term_for_index(
                                next_index_for_this_server-1),
                            leader_commit=self._log.commit_index(),
                            log_entries=entries_to_send)

                    self._print('Received append entries response from '
                                f'{server}: Success={resp.success}')

                    if resp.success:
                        self._state.next_index[server] = \
                            entries_to_send[-1].index + 1
                        self._state.match_index[server] = \
                            entries_to_send[-1].index
                        return server
                    else:
                        self._state.next_index[server] -= 1
            except TimeoutError:
                self._print(f'Append entries request to server {server} timed '
                            'out; retrying')

    async def _append_entries(self: Self) -> None:
        """ Attempt to replicate new entries on a majority of the
        cluster by sending AppendEntries requests to the other nodes.
        As soon as that's done, we can commit the new entries; however,
        for any nodes that haven't acknowledged replication we'll need
        to keep retrying.
        """
        match self._state:
            case FollowerState() | CandidateState():
                self._print('Bug: attempting to append entries while not in '
                            'Leader state')
                sys.exit(1)
            case LeaderState():
                replications: int = 1
                replication_requests: list[asyncio.Task] = []
                for server in self.config.all_raft_server_ports:
                    if server != self.config.raft_server_port:
                        server_task = \
                            asyncio.create_task(
                                    self._append_entries_on_one_server(server))
                        self._state.append_entries_tasks[server] = server_task
                        replication_requests.append(server_task)

                for fut in asyncio.as_completed(replication_requests):
                    server = await(fut)
                    del self._state.append_entries_tasks[server]
                    replications += 1

                    if replications > \
                            len(self.config.all_raft_server_ports) / 2:
                        return

    def _update_commit_index(self):
        """ We can update our commit index once there is a higher index
        that's been replicated on a majority of servers.
        """
        assert isinstance(self._state, LeaderState)
        match_indices = sorted([self._state.match_index[port]
                                for port in self.config.all_raft_server_ports
                                if port != self.config.raft_server_port])
        halfway_point = int(len(self.config.all_raft_server_ports) / 2)
        min_with_majority = match_indices[halfway_point]
        if min_with_majority > self._log.commit_index() \
            and self._log.term_for_index(min_with_majority) == \
                self._current_term:
            self._print(f'New commit index: {min_with_majority}')
            self._log.set_commit_index(min_with_majority)

    async def _propose_mapping_handler(self: Self, mapping: Mapping) \
            -> ProposeMappingResponse:
        """ If we aren't the leader, let the proposer know who they should
        talk to. Otherwise append the new mapping locally and attempt to
        apply it to the state machine by sending AppendEntries requests to
        all other nodes.
        """
        match self._state:
            case FollowerState(leader=leader):
                return ProposeMappingResponse(success=False,
                                              current_leader=leader)
            case CandidateState():
                return ProposeMappingResponse(success=False,
                                              current_leader=None)
            case LeaderState():
                self._print('Received mapping proposal: '
                            f'{mapping.key}={mapping.value}')
                self._log.add_new_entry(term=self._current_term,
                                        key=mapping.key,
                                        value=mapping.value)
                await self._append_entries()
                self._print(f'Mapping {mapping.key}={mapping.value} '
                            'successfully replicated; updating commit index')
                self._update_commit_index()
                return ProposeMappingResponse(
                    success=True,
                    current_leader=self.config.raft_server_port)
            case _:
                assert False

    def _become_follower(self: Self, new_leader: int | None) -> None:
        """ A follower will remain as such for as long as a leader is
        heartbeating. If the heartbeat loop ever times out, become
        a candidate.
        """
        match self._state:
            case FollowerState(leader) if leader is not None:
                self._state.leader = new_leader
            case FollowerState() | CandidateState() | LeaderState():
                self._state.teardown()
                self._state = FollowerState(leader=new_leader)
                run_in_background(self._wait_for_next_heartbeat())

    async def _wait_for_next_heartbeat(self: Self) -> None:
        """ Set up a task that will hopefully be cancelled by an
        incoming RPC request from a leader within the allotted
        heartbeat timeout. If it isn't, transition to candidate
        state. Otherwise, wait for another heartbeat.
        """
        loop = asyncio.get_event_loop()

        match self._state:
            # No way to get into candidate state outside of a heartbeat
            # timeout, and no way to get into leader state outside of
            # winning an election
            case LeaderState() | CandidateState():
                pass

            case FollowerState():
                if self._state.receive_heartbeats_task is not None:
                    # self._print('Heartbeat received. Cancelling old task')
                    self._state.receive_heartbeats_task.cancel()

                wait_for_heartbeat = \
                    asyncio.sleep(self.config.heartbeat_timeout_ms / 1000)
                self._state.receive_heartbeats_task = \
                    loop.create_task(wait_for_heartbeat)

                try:
                    await(self._state.receive_heartbeats_task)
                    self._state.receive_heartbeats_task = None
                    self._print('Heartbeat timeout. Becoming a candidate')
                    self._become_candidate()
                except CancelledError:
                    # Heartbeat received
                    # self._print('Heartbeat task cancelled')
                    pass

    async def _hold_election(self: Self) -> None:
        """ Send VoteRequests to all other nodes. If in the middle
        of the election we receive an RPC from a node with a
        greater or equal term, we'll know another leader was
        elected and we should instead become a follower.

        If we don't win, we expect another node to win and
        thus their next heartbeat should cancel the election.
        If no other node wins, the election will time out and
        we'll try again.
        """
        self._current_term += 1
        self._voted_for = self.config.raft_server_port
        self._print(f'Starting election for term {self._current_term}')

        last_log_index, last_log_term = self._log.last_index_and_term()
        votes: int = 1
        self._print('Sending vote requests to '
                    f'{len(self._raft_rpc_clients.values())} clients')
        vote_requests: Iterable[Coroutine[Any, Any, RequestVoteResponse]] = [
                client.request_vote(
                    term=self._current_term,
                    candidate_id=self.config.raft_server_port,
                    last_log_index=last_log_index,
                    last_log_term=last_log_term)
                for client in self._raft_rpc_clients.values()
                ]

        for coro in asyncio.as_completed(vote_requests):
            result: RequestVoteResponse = await(coro)
            if result.vote_granted:
                votes += 1
                if votes > len(self.config.all_raft_server_ports) / 2:
                    self._print('Threshold met - returning from election')
                    return

        # If we didn't get a majority of votes, sleep ~forever and
        # wait for either the new leader or the election timeout.
        await asyncio.sleep(10000000)

    async def _election_loop(self: Self) -> None:
        """ Hold elections repeatedly until we win or someone else does.
        """
        election_timeout_ms = \
            random.randrange(self.config.min_election_timeout_ms,
                             self.config.max_election_timeout_ms+1)

        while True:
            try:
                async with asyncio.timeout(election_timeout_ms / 1000):
                    # Only returns if we've won the election. A new
                    # leader's heartbeat will cancel the entire election
                    # loop, not just this election.
                    await self._hold_election()
                    self._print('Election won! Becoming leader')
                    run_in_background(self._become_leader())
                    break

            except TimeoutError:
                self._print('Election timed out. Trying again')

    def _become_candidate(self: Self) -> None:
        """ Change the state and start an election.
        """
        election_task = run_in_background(self._election_loop())
        self._state = CandidateState(election_task)

    def _send_heartbeats(self: Self) -> None:
        """ Send one heartbeat to all other nodes.
        """
        prev_log_index, prev_log_term = self._log.last_index_and_term()

        for client in self._raft_rpc_clients.values():
            heartbeat_coro = \
                client.append_entries(
                    term=self._current_term,
                    leader_id=self.config.raft_server_port,
                    prev_log_index=prev_log_index,
                    prev_log_term=prev_log_term,
                    leader_commit=self._log.commit_index(),
                    log_entries=[]
                    )

            run_in_background(heartbeat_coro)

    async def _become_leader(self: Self) -> None:
        """ Change state and start sending heartbeats.
        """
        self._print('Starting heartbeat loop')
        heartbeat_interval = self.config.heartbeat_timeout_ms / 2
        heartbeat_loop_done = \
            run_every(self._send_heartbeats,
                      timedelta(milliseconds=heartbeat_interval))
        last_log_index = self._log.last_index_and_term()[0]
        self._state = LeaderState(all_ports=self.config.all_raft_server_ports,
                                  my_port=self.config.raft_server_port,
                                  last_log_index=last_log_index,
                                  heartbeat_loop_done=heartbeat_loop_done)

        try:
            await heartbeat_loop_done
        except CancelledError:
            # Do nothing - another node has become the leader and
            # its heartbeat will cause us to transition to Follower status
            return

        self._print('Bug: heartbeat loop completed')

    async def startup(self: Self) -> None:
        self._print('Starting up')
        # Load persistent state from disk
        await self._load_persistent_state()

        await self._raft_rpc_server.serve()
        self._become_follower(self._voted_for)
        await self._cluster_rpc_server.serve()
        await self._raft_rpc_server.wait_for_termination()
