"""Privacy-safe verification of an executed R3000A JR $ra return boundary.

Uses the concrete interpreter's completed control-transfer trace.  In
particular, seeing a JR opcode in code or visiting a return PC is not enough:
its delay-slot instruction must have executed successfully and the guest must
stop immediately at the branch target with no pending delayed load.
"""


def verify(trace, expected_stop_pc):
    """Return bounded boolean evidence, never guest addresses or values."""
    if type(expected_stop_pc) is not int or not 0 <= expected_stop_pc <= 0xffffffff or expected_stop_pc & 3:
        raise ValueError('invalid expected return boundary')
    if not isinstance(trace, dict):
        raise ValueError('invalid execution report')
    visited = trace.get('visited_pcs')
    transfers = trace.get('control_transfers')
    if not isinstance(visited, (tuple, list)) or not isinstance(transfers, (tuple, list)):
        raise ValueError('missing executed guest control-flow evidence')
    for pc in visited:
        if type(pc) is not int or pc < 0 or pc & 3:
            raise ValueError('malformed instruction visit')
    for event in transfers:
        if (not isinstance(event, (tuple, list)) or len(event) != 3 or
                type(event[0]) is not int or type(event[2]) is not int or
                not isinstance(event[1], str)):
            raise ValueError('malformed completed transfer')
    stopped = (trace.get('completed') is True and
               trace.get('reason') == 'stop_pc' and
               trace.get('pc') == expected_stop_pc)
    is_jr = bool(transfers and transfers[-1][1] == 'jr_ra'
                 and transfers[-1][2] == expected_stop_pc)
    slot_completed = bool(is_jr and len(visited) >= 2 and
                          visited[-2:] == (transfers[-1][0],
                                           transfers[-1][0] + 4))
    load_drained = trace.get('pending_load') is None
    return {
        'guest_stopped_at_expected_pc': stopped,
        'last_completed_transfer_is_jr_ra_to_stop': is_jr,
        'jr_ra_delay_slot_executed_last': slot_completed,
        'no_pending_delayed_load_at_stop': load_drained,
        'verified_complete_jr_ra_return': bool(stopped and is_jr and
                                               slot_completed and load_drained),
        'original_hardware_return_verified': False,
        'private_values_emitted': False,
    }
