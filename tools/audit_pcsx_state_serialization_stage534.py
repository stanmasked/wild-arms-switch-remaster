#!/usr/bin/env python3
"""Classify narrowly bounded PCSX-Redux savestate diffs in CD-ROM response FIFO payload tails.

This parser validates protobuf wire structure for SaveState -> CDRom -> responseFifo0
only. It is not a full savestate validator and does not attest gameplay or hardware parity.
"""
import argparse
import hashlib
import json
from pathlib import Path
import stat

MAX_STATE_BYTES = 64 * 1024 * 1024
PAYLOAD_LENGTH = 16


def read_state(path):
    path = Path(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= MAX_STATE_BYTES:
        raise ValueError("savestate must be a bounded regular single-link file")
    data = path.read_bytes()
    if len(data) != info.st_size:
        raise ValueError("savestate size changed while reading")
    return data


def read_varint(data, pos, end):
    value = 0
    shift = 0
    for _ in range(10):
        if pos >= end:
            raise ValueError("truncated protobuf varint")
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7f) << shift
        if not (byte & 0x80):
            return value, pos
        shift += 7
    raise ValueError("protobuf varint exceeds ten bytes")


def parse_fields(data, start=0, end=None):
    if end is None:
        end = len(data)
    if type(start) is not int or type(end) is not int or not 0 <= start <= end <= len(data):
        raise ValueError("invalid protobuf message bounds")
    fields = []
    pos = start
    while pos < end:
        field_start = pos
        tag, pos = read_varint(data, pos, end)
        number, wire = tag >> 3, tag & 7
        if number == 0:
            raise ValueError("protobuf field number zero")
        if wire == 0:
            value, pos = read_varint(data, pos, end)
            fields.append({"number": number, "wire": wire, "start": field_start, "end": pos,
                           "value": value})
        elif wire == 1:
            if pos + 8 > end:
                raise ValueError("truncated fixed64 field")
            fields.append({"number": number, "wire": wire, "start": field_start, "end": pos+8,
                           "value_start": pos, "value_end": pos+8, "value": data[pos:pos+8]})
            pos += 8
        elif wire == 2:
            length, pos = read_varint(data, pos, end)
            payload_start = pos
            payload_end = payload_start + length
            if payload_end > end:
                raise ValueError("protobuf length-delimited field exceeds message")
            fields.append({"number": number, "wire": wire, "start": field_start, "end": payload_end,
                           "value_start": payload_start, "value_end": payload_end,
                           "length": length, "value": data[payload_start:payload_end]})
            pos = payload_end
        elif wire == 5:
            if pos + 4 > end:
                raise ValueError("truncated fixed32 field")
            fields.append({"number": number, "wire": wire, "start": field_start, "end": pos+4,
                           "value_start": pos, "value_end": pos+4, "value": data[pos:pos+4]})
            pos += 4
        else:
            raise ValueError("unsupported protobuf wire type")
    if pos != end:
        raise ValueError("protobuf parser did not consume message")
    return fields


def one_field(fields, number, wire, label):
    found = [item for item in fields if item["number"] == number]
    if len(found) != 1 or found[0]["wire"] != wire:
        raise ValueError("missing, duplicate, or wrong-wire protobuf field: " + label)
    return found[0]


def locate_response_payload(data):
    top = parse_fields(data)
    state_info = one_field(top, 1, 2, "SaveState.save_state_info")
    info_fields = parse_fields(data, state_info["value_start"], state_info["value_end"])
    version_string = one_field(info_fields, 1, 2, "SaveStateInfo.version_string")
    version = one_field(info_fields, 2, 0, "SaveStateInfo.version")
    if data[version_string["value_start"]:version_string["value_end"]] != b"PCSX-Redux SaveState v5" or version["value"] != 5:
        raise ValueError("savestate does not match the pinned PCSX-Redux v5 protobuf envelope")
    cdrom = one_field(top, 15, 2, "SaveState.cdrom")
    cdrom_fields = parse_fields(data, cdrom["value_start"], cdrom["value_end"])
    response = one_field(cdrom_fields, 46, 2, "CDRom.responseFifo0")
    queue_fields = parse_fields(data, response["value_start"], response["value_end"])
    if len(queue_fields) != 7 or {item["number"] for item in queue_fields} != set(range(1, 8)):
        raise ValueError("unexpected CD-ROM response FIFO queue schema")
    if len({item["number"] for item in queue_fields}) != len(queue_fields):
        raise ValueError("duplicate CD-ROM response FIFO queue field")
    payload = one_field(queue_fields, 1, 2, "responseFifo0.payload")
    payload_size = one_field(queue_fields, 6, 0, "responseFifo0.payload_size")
    payload_index = one_field(queue_fields, 7, 0, "responseFifo0.payload_index")
    if payload["length"] != PAYLOAD_LENGTH:
        raise ValueError("CD-ROM response FIFO payload is not fixed 16 bytes")
    if payload_size["value"] > PAYLOAD_LENGTH or payload_index["value"] > PAYLOAD_LENGTH:
        raise ValueError("CD-ROM response FIFO payload size/index out of range")
    return {"payload_start": payload["value_start"], "payload_end": payload["value_end"],
            "payload": payload["value"], "payload_size": payload_size["value"],
            "payload_index": payload_index["value"], "queue_fields": queue_fields}


def audit_pair(before_path, after_path):
    before = read_state(before_path)
    after = read_state(after_path)
    if len(before) != len(after):
        raise ValueError("savestate sizes differ")
    if before == after:
        raise ValueError("no savestate serialization difference to classify")
    a = locate_response_payload(before)
    b = locate_response_payload(after)
    if a["payload_size"] != b["payload_size"] or a["payload_index"] != b["payload_index"]:
        raise ValueError("active response FIFO size/index differ")
    if a["payload"][:a["payload_size"]] != b["payload"][:b["payload_size"]]:
        raise ValueError("active response FIFO payload prefix differs")
    if a["payload_start"] != b["payload_start"] or a["payload_end"] != b["payload_end"]:
        raise ValueError("response FIFO payload offsets differ")
    diffs = [i for i, (x, y) in enumerate(zip(before, after)) if x != y]
    if not diffs:
        raise ValueError("savestate difference could not be located")
    inactive_start = a["payload_start"] + a["payload_size"]
    inactive_end = a["payload_end"]
    if any(not inactive_start <= i < inactive_end for i in diffs):
        raise ValueError("savestate difference escapes unused response FIFO payload tail")
    queue_metadata_equal = len(a["queue_fields"]) == len(b["queue_fields"])
    for fa, fb in zip(a["queue_fields"], b["queue_fields"]):
        if fa["number"] == 1:
            continue
        if fa != fb:
            queue_metadata_equal = False
            break
    if not queue_metadata_equal:
        raise ValueError("response FIFO queue metadata differs")
    changed_payload_indices = [i-a["payload_start"] for i in diffs]
    return {
        "kind": "PCSX_REDUX_SAVESTATE_UNUSED_RESPONSE_FIFO_TAIL_DIFF",
        "schema": 1,
        "status": "PASS_DIFFS_ONLY_IN_UNUSED_CDRom_RESPONSEFIFO0_PAYLOAD_TAIL",
        "before_size": len(before),
        "after_size": len(after),
        "before_sha256": hashlib.sha256(before).hexdigest(),
        "after_sha256": hashlib.sha256(after).hexdigest(),
        "changed_byte_count": len(diffs),
        "changed_file_offsets": diffs,
        "changed_payload_indices": changed_payload_indices,
        "payload_size": a["payload_size"],
        "payload_index": a["payload_index"],
        "active_payload_prefix_equal": True,
        "response_fifo_metadata_equal": queue_metadata_equal,
        "all_differences_outside_active_payload_prefix": True,
        "classification_limit": "This classifies protobuf bytes only; it is not gameplay or hardware-parity attestation.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before_state")
    parser.add_argument("after_state")
    parser.add_argument("--output", help="optional JSON report path")
    args = parser.parse_args()
    try:
        result = audit_pair(args.before_state, args.after_state)
    except (ValueError, OSError):
        parser.exit(2, "UNCLASSIFIED_SAVESTATE_DIFFERENCE\n")
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        target = Path(args.output)
        if target.exists() or target.is_symlink():
            parser.exit(2, "REFUSE_TO_OVERWRITE_REPORT\n")
        target.write_text(text, encoding="utf-8")
    print("SAVESTATE_DIFF_LOCALIZED_TO_UNUSED_RESPONSE_FIFO_TAIL; NOT_GAMEPLAY_ATTESTATION")
    print("changed_bytes", result["changed_byte_count"], "payload_size", result["payload_size"],
          "changed_payload_indices", result["changed_payload_indices"])


if __name__ == "__main__":
    main()
