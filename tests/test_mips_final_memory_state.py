"""Fully synthetic RAM block checks and differential outside-matrix side effects."""
import hashlib
import unittest

from tools.mips_final_memory_state import (
    BLOCK_SIZE, pack, decode, compare, snapshot, changed_outside_matrix)
from tools.mips_matrix_memory import MappedMemory

RAM=0x80110000
MATRIX=RAM+32


def reference(size=128, *, modified=()):
    before=bytes(size)
    after=bytearray(before)
    for offset, value in modified:
        after[offset]=value
    return before, bytes(after), decode(pack(before,bytes(after),RAM,MATRIX),MATRIX)


class MemoryStateTests(unittest.TestCase):
    def test_exact_ram_match(self):
        before,after,ref=reference(modified=[(32,1),(33,16),(91,7)])
        m=MappedMemory().map_region(RAM,after,writable=True)
        r=compare(m,ref,before,guest_stopped_at_expected_pc=True,matrix_address=MATRIX)
        self.assertTrue(r['matches_reference'])
        self.assertEqual(r['mismatching_block_indices'],[])
        self.assertEqual(r['expected_changed_bytes_outside_matrix'],1)
        self.assertEqual(r['observed_changed_bytes_outside_matrix'],1)
        self.assertFalse(r['external_ps1_hardware_authenticated'])

    def test_side_effect_missing_outside_matrix(self):
        before,after,ref=reference(modified=[(32,1),(95,7)])
        m=MappedMemory().map_region(RAM,after[:95]+b'\x00'+after[96:])
        r=compare(m,ref,before,guest_stopped_at_expected_pc=True,matrix_address=MATRIX)
        self.assertEqual(r['mismatching_block_indices'],[0])
        self.assertEqual(r['expected_changed_bytes_outside_matrix'],1)
        self.assertEqual(r['observed_changed_bytes_outside_matrix'],0)
        self.assertFalse(r['matches_reference'])

    def test_unexpected_unmodeled_memory_change(self):
        before,after,ref=reference()
        changed=bytearray(after); changed[127]=45
        m=MappedMemory().map_region(RAM,changed)
        r=compare(m,ref,before,guest_stopped_at_expected_pc=True,matrix_address=MATRIX)
        self.assertEqual(r['observed_changed_bytes_outside_matrix'],1)
        self.assertFalse(r['matches_reference'])

    def test_matrix_changes_excluded_from_external_side_effect_count(self):
        before,after,ref=reference(modified=[(32,1),(33,255),(49,200)])
        self.assertEqual(ref['expected_changed_bytes_outside_matrix'],0)
        self.assertEqual(changed_outside_matrix(before,after,RAM,MATRIX),0)

    def test_block_index_only_second_block(self):
        before,after,ref=reference(2*BLOCK_SIZE,modified=[(BLOCK_SIZE+7,25)])
        actual=bytearray(after);actual[BLOCK_SIZE+7]=26
        m=MappedMemory().map_region(RAM,actual)
        result=compare(m,ref,before,guest_stopped_at_expected_pc=True,matrix_address=MATRIX)
        self.assertEqual(result['mismatching_block_indices'],[1])
        self.assertEqual(result['checked_block_count'],2)
        self.assertNotIn('26',str(result))

    def test_partial_last_block_hash(self):
        before,after,ref=reference(BLOCK_SIZE+17,modified=[(BLOCK_SIZE+16,123)])
        self.assertEqual(len(ref['hashes']),2)
        m=MappedMemory().map_region(RAM,after)
        self.assertTrue(compare(m,ref,before,guest_stopped_at_expected_pc=True,matrix_address=MATRIX)['matches_reference'])

    def test_eager_validation_rejects_missing_or_corrupt_block(self):
        before,after,ref=reference(2*BLOCK_SIZE)
        raw=pack(before,after,RAM,MATRIX)
        for hashes in ([],raw['block_sha256'][:-1],['a'*64],['Z'*64]*2,[123]*2):
            bad={**raw,'block_sha256':hashes}
            with self.subTest(hashes=hashes),self.assertRaises(ValueError):
                decode(bad,MATRIX)

    def test_strict_keys_no_unbounded_or_unknown_metadata(self):
        before,after,ref=reference()
        raw=pack(before,after,RAM,MATRIX)
        raw['secret']='private'
        with self.assertRaises(ValueError): decode(raw,MATRIX)

    def test_reject_invalid_sizes_bases_and_counts(self):
        before,after,_=reference()
        for key,value in [('address',True),('address',-1),('size',17),('size',2**32),
                          ('block_size',512),('block_size',True),
                          ('expected_changed_bytes_outside_matrix',-1),
                          ('expected_changed_bytes_outside_matrix',129)]:
            raw=pack(before,after,RAM,MATRIX); raw[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                decode(raw,MATRIX)

    def test_reject_missing_full_before_ram(self):
        before,after,ref=reference()
        m=MappedMemory().map_region(RAM,after)
        with self.assertRaises(ValueError):
            compare(m,ref,before[:-1],guest_stopped_at_expected_pc=True,matrix_address=MATRIX)

    def test_unmapped_gap_is_rejected_not_zero_filled(self):
        before,after,ref=reference()
        m=MappedMemory().map_region(RAM,after[:64]).map_region(RAM+65,after[65:])
        with self.assertRaises(ValueError):
            compare(m,ref,before,guest_stopped_at_expected_pc=True,matrix_address=MATRIX)

    def test_mapped_adjacent_regions_do_not_require_single_region(self):
        before,after,ref=reference(modified=[(70,13)])
        m=MappedMemory().map_region(RAM+64,after[64:]).map_region(RAM,after[:64])
        self.assertTrue(compare(m,ref,before,guest_stopped_at_expected_pc=True,matrix_address=MATRIX)['matches_reference'])

    def test_nonstop_execution_withholds_all_mismatches(self):
        before,after,ref=reference(modified=[(95,1)])
        m=MappedMemory().map_region(RAM,b'\xff'*128)
        r=compare(m,ref,before,guest_stopped_at_expected_pc=False,matrix_address=MATRIX)
        self.assertFalse(r['comparison_performed'])
        self.assertIsNone(r['observed_changed_bytes_outside_matrix'])
        self.assertEqual(r['mismatching_block_indices'],[])

    def test_boolean_stop_required(self):
        before,after,ref=reference()
        m=MappedMemory().map_region(RAM,after)
        with self.assertRaises(ValueError):
            compare(m,ref,before,guest_stopped_at_expected_pc=1,matrix_address=MATRIX)

    def test_output_omits_addresses_hashes_bytes(self):
        before,after,ref=reference(modified=[(126,77)])
        m=MappedMemory().map_region(RAM,after)
        output=compare(m,ref,before,guest_stopped_at_expected_pc=True,matrix_address=MATRIX)
        self.assertNotIn(hex(RAM),str(output))
        self.assertNotIn(ref['hashes'][0],str(output))
        self.assertFalse(output['private_values_emitted'])

    def test_2mib_guest_ram_fast_complete_match(self):
        size=2*1024*1024
        before=bytes(size)
        after=bytearray(before)
        after[MATRIX-RAM:MATRIX-RAM+2]=b'\x00\x10'
        after[500000]=19
        ref=decode(pack(before,bytes(after),RAM,MATRIX),MATRIX)
        m=MappedMemory().map_region(RAM,after)
        r=compare(m,ref,before,guest_stopped_at_expected_pc=True,matrix_address=MATRIX)
        self.assertTrue(r['matches_reference'])
        self.assertEqual(r['checked_block_count'],512)
        self.assertEqual(r['observed_changed_bytes_outside_matrix'],1)


if __name__=='__main__':unittest.main()
