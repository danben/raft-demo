# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: raft.proto
"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database

# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(
    b'\n\nraft.proto"`\n\x0bVoteRequest\x12\x0c\n\x04term\x18\x01 \x01(\x05\x12\x14\n\x0crequester_id\x18\x02 \x01(\x05\x12\x16\n\x0elast_log_index\x18\x03 \x01(\x05\x12\x15\n\rlast_log_term\x18\x04 \x01(\x05"9\n\x13RequestVoteResponse\x12\x0c\n\x04term\x18\x01 \x01(\x05\x12\x14\n\x0cvote_granted\x18\x02 \x01(\x08"C\n\x08LogEntry\x12\x0c\n\x04term\x18\x01 \x01(\x05\x12\r\n\x05index\x18\x02 \x01(\x05\x12\x0b\n\x03key\x18\x03 \x01(\t\x12\r\n\x05value\x18\x04 \x01(\t"\xa0\x01\n\x14\x41ppendEntriesRequest\x12\x0c\n\x04term\x18\x01 \x01(\x05\x12\x14\n\x0crequester_id\x18\x02 \x01(\x05\x12\x16\n\x0eprev_log_index\x18\x03 \x01(\x05\x12\x15\n\rprev_log_term\x18\x04 \x01(\x05\x12\x15\n\rleader_commit\x18\x05 \x01(\x05\x12\x1e\n\x0blog_entries\x18\x06 \x03(\x0b\x32\t.LogEntry"6\n\x15\x41ppendEntriesResponse\x12\x0c\n\x04term\x18\x01 \x01(\x05\x12\x0f\n\x07success\x18\x02 \x01(\x08"%\n\x07Mapping\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t"Y\n\x16ProposeMappingResponse\x12\x0f\n\x07success\x18\x01 \x01(\x08\x12\x1b\n\x0e\x63urrent_leader\x18\x02 \x01(\x05H\x00\x88\x01\x01\x42\x11\n\x0f_current_leader"\x12\n\x03Key\x12\x0b\n\x03key\x18\x01 \x01(\t"=\n\x10GetValueResponse\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\x12\n\x05value\x18\x02 \x01(\tH\x00\x88\x01\x01\x42\x08\n\x06_value2}\n\x04Raft\x12\x33\n\x0bRequestVote\x12\x0c.VoteRequest\x1a\x14.RequestVoteResponse"\x00\x12@\n\rAppendEntries\x12\x15.AppendEntriesRequest\x1a\x16.AppendEntriesResponse"\x00\x32g\n\x07\x43luster\x12\x35\n\x0eProposeMapping\x12\x08.Mapping\x1a\x17.ProposeMappingResponse"\x00\x12%\n\x08GetValue\x12\x04.Key\x1a\x11.GetValueResponse"\x00\x62\x06proto3'
)

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, "raft_pb2", globals())
if _descriptor._USE_C_DESCRIPTORS == False:
    DESCRIPTOR._options = None
    _VOTEREQUEST._serialized_start = 14
    _VOTEREQUEST._serialized_end = 110
    _REQUESTVOTERESPONSE._serialized_start = 112
    _REQUESTVOTERESPONSE._serialized_end = 169
    _LOGENTRY._serialized_start = 171
    _LOGENTRY._serialized_end = 238
    _APPENDENTRIESREQUEST._serialized_start = 241
    _APPENDENTRIESREQUEST._serialized_end = 401
    _APPENDENTRIESRESPONSE._serialized_start = 403
    _APPENDENTRIESRESPONSE._serialized_end = 457
    _MAPPING._serialized_start = 459
    _MAPPING._serialized_end = 496
    _PROPOSEMAPPINGRESPONSE._serialized_start = 498
    _PROPOSEMAPPINGRESPONSE._serialized_end = 587
    _KEY._serialized_start = 589
    _KEY._serialized_end = 607
    _GETVALUERESPONSE._serialized_start = 609
    _GETVALUERESPONSE._serialized_end = 670
    _RAFT._serialized_start = 672
    _RAFT._serialized_end = 797
    _CLUSTER._serialized_start = 799
    _CLUSTER._serialized_end = 902
# @@protoc_insertion_point(module_scope)
