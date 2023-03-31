# raft-demo
Toy implementation of the Raft consensus algorithm for a simple key-value store.

## Overview
This amounts to much of the algorithm described in the [Raft paper](https://raft.github.io/raft.pdf). The software represents a single node; running a sufficient number and informing them of each other amounts to a functioning cluster. This is not intended as a real production-quality piece of software; rather it was a learning experience / proof of concept for me and as such the nodes narrate their behavior loudly to stdout so one can follow along. Testing is so far scant and there are likely subtle bugs waiting to be discovered.

## Requirements
Tested under Python 3.11 on Ubuntu, though 3.10 is likely sufficient. 

Third party libraries:
[aiofiles](https://pypi.org/project/aiofiles/)
[grpc](https://grpc.io/docs/languages/python/quickstart/)
[uvloop](https://pypi.org/project/uvloop/)

(Or use `requirements.txt` - most of what's in there is only for typing)

## Features (and lack thereof)

This implementation focuses only on the two most important pieces of the Raft algorithm: leader election and log replication. Other features, notably log compaction, are not included. The state machine is a key-value store, where each command from a client adds a mapping. A new mapping for a key will overwrite any previous mappings for the same key. Deleting keys is not supported.

## Implementation / Quirks

Each node acts as a server for two separate gRPC services - one that handles communication between nodes and another that responds to client requests. There are two RPCs for node communication: VoteRequest and AppendEntries. The former is used to elect a leader and the latter allows the leader to replicate log entries on the other nodes.

The second service exposes two RPCs to clients outside of the cluster: GetValue and ProposeMapping. Only the current leader can accept a mapping proposal; the client will start by picking a node randomly and a non-leader will redirect the client to the current leader. All nodes are allowed to respond to GetValue requests - this means that a client might see a stale value for a key if replication has not yet completed.

Though this is not strictly prescribed by the algorithm (in-memory-only state machines are permitted), in this implementation the log is persisted to disk.

Since this isn't meant to be used in earnest, I took a few shortcuts (all of which could easily be unwound):

- Nodes are identified fully by the port they listed on for Raft RPC requests. This is possible under the assumption that they'll always run on localhost (an assumption presently baked in, as it's not possible to specify an IP address to connect to).
- Since there is no log compaction, there is an invariant that the index of a log entry is the same as its (0-indexed) position in the log.

## Trying it out

If you're brave enough to run code that I've written on your own machine, the easiest thing to do is to just run test_harness.py (possibly editing the top to specify a port range and log directory, and the bottom to select the test you'd like to run - there are currently two!) This will bring up a cluster of five nodes in separate processes, run the test, and bring all of the nodes down again.

# Miscellaneous

- Formatting by [black](https://pypi.org/project/black/).
- I replaced the default async executor with uvloop, which is supposed to improve performance in asyncio applications in general.