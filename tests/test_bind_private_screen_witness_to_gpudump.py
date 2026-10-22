"""Stage452 ROM-free witness-screen vs native first-frame VRAM-state gate."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from bind_private_screen_witness_to_gpudump import (
    bind_private_screen_witness_to_gpu_dump)
from capture_private_pcsx_frame_witness import (
    capture_private_frame_witness,verify_private_frame_witness)
from test_capture_private_pcsx_frame_witness import (
    expected_sequence,fake_vram,fake_png)
from test_verify_private_pcsx_native_gpudump_import import (
    prepared,ID)
from test_import_private_pcsx_native_gpudump import base_records
from import_private_pcsx_native_gpudump import GP0,VSYNC


def setup(root,*,vram_bytes=None,native_records=None):
    base=Path(root)
    witness=base/"witness";witness.mkdir()
    capture_private_frame_witness(
        witness,basename="surf",
        opener=expected_sequence(
            first=bytes(1024*1024) if vram_bytes is None else vram_bytes,
            second=bytes(1024*1024) if vram_bytes is None else vram_bytes))
    game=base/"gpu";game.mkdir()
    native,pre,trace=prepared(game,records=native_records)
    return witness,native,pre,trace


def bind(witness,native,pre,trace,**kwargs):
    return bind_private_screen_witness_to_gpu_dump(
        witness,"surf",native,pre,trace,**kwargs)


class Stage452PausedScreenBindingTests(unittest.TestCase):
    def test_matching_1mib_vram_yields_state_equality_not_frame_attestation(self):
        with tempfile.TemporaryDirectory() as td:
            witness,native,pre,trace=setup(td)
            r=bind(witness,native,pre,trace,expected_frame=449,
                   expected_native_game_id=ID,
                   expected_native_sha256=hashlib.sha256(
                       native.read_bytes()).hexdigest(),
                   expected_screen_sha256=hashlib.sha256(fake_png()).hexdigest(),
                   expected_completed_frames=1)
            self.assertEqual(r["status"],
                "EXACT_VRAM_STATE_EQUALITY_WITH_UNVERIFIED_FRAME_ALIGNMENT")
            self.assertTrue(r["paused_and_native_initial_vram_sha256_equal"])
            self.assertTrue(r["native_gp0_vram_vsync_binding_verified"])
            self.assertTrue(r["stage432_screen_png_disc_and_vram_integrity_verified_twice"])
            self.assertTrue(r["interpretation"]["equal_vram_states_are_not_proof_of_same_frame"])
            self.assertTrue(r["interpretation"]["native_first_vsync_not_proven_same_as_paused_screenshot"])

    def test_paused_screen_has_an_independent_png_hash(self):
        with tempfile.TemporaryDirectory() as td:
            witness,native,pre,trace=setup(td)
            report=bind(witness,native,pre,trace)
            self.assertEqual(report["paused_screenshot_png_sha256"],
                             hashlib.sha256(fake_png()).hexdigest())
            self.assertEqual(report["paused_witness_vram_sha256"],
                             report["native_initial_vram_sha256"])
            self.assertNotEqual(report["paused_screenshot_png_sha256"],
                                report["paused_witness_vram_sha256"])

    def test_distinct_vram_witness_strictly_rejected_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            witness,native,pre,trace=setup(td,vram_bytes=fake_vram())
            with self.assertRaisesRegex(ValueError,"VRAM differs"):
                bind(witness,native,pre,trace)

    def test_opt_in_mismatch_is_explicitly_unbound(self):
        with tempfile.TemporaryDirectory() as td:
            witness,native,pre,trace=setup(td,vram_bytes=fake_vram())
            report=bind(witness,native,pre,trace,
                        require_exact_vram_match=False)
            self.assertEqual(report["status"],
                             "DIFFERENT_VRAM_STATES_NO_FRAME_BINDING")
            self.assertFalse(report["paused_and_native_initial_vram_sha256_equal"])
            self.assertFalse(report["exact_vram_equality_required"])

    def test_identical_paused_vram_does_not_automatically_authenticate_scene(self):
        with tempfile.TemporaryDirectory() as td:
            witness,native,pre,trace=setup(td)
            r=bind(witness,native,pre,trace)
            self.assertTrue(r["interpretation"][
                "operator_scene_label_is_not_authenticated_map_identity"])
            self.assertTrue(r["interpretation"][
                "screenshot_render_may_precede_pause_and_gpu_capture"])

    def test_mismatched_independent_expected_screenshot_hash_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            witness,native,pre,trace=setup(td)
            with self.assertRaisesRegex(ValueError,"expected screenshot SHA256"):
                bind(witness,native,pre,trace,expected_screen_sha256="0"*64)

    def test_invalid_screenshot_hash_format_is_rejected_before_io(self):
        with tempfile.TemporaryDirectory() as td:
            witness,native,pre,trace=setup(td)
            for value in (True,b"0"*64,"UPPERCASE","00",0):
                with self.subTest(value=value),self.assertRaisesRegex(ValueError,"invalid strict"):
                    bind(witness,native,pre,trace,expected_screen_sha256=value)

    def test_mutated_original_png_fails_even_if_vram_matches(self):
        with tempfile.TemporaryDirectory() as td:
            witness,native,pre,trace=setup(td)
            screen=witness/"surf.screen.png"
            altered=bytearray(screen.read_bytes())
            altered[25]^=1
            screen.write_bytes(altered)
            with self.assertRaises(ValueError):
                bind(witness,native,pre,trace)

    def test_mutated_original_cd_info_fails_before_binding(self):
        with tempfile.TemporaryDirectory() as td:
            witness,native,pre,trace=setup(td)
            disc=witness/"surf.cdinfo.json"
            disc.write_bytes(b'{"disc":"different"}')
            with self.assertRaisesRegex(ValueError,"hash mismatch"):
                bind(witness,native,pre,trace)

    def test_mutated_witness_vram_refused_before_native_integrity(self):
        with tempfile.TemporaryDirectory() as td:
            witness,native,pre,trace=setup(td)
            vram=witness/"surf.u16le.bin"
            mutated=bytearray(vram.read_bytes());mutated[1818]=5
            vram.write_bytes(mutated)
            with self.assertRaisesRegex(ValueError,"hash mismatch"):
                bind(witness,native,pre,trace)

    def test_native_gp0_jsonl_tampering_not_masked_by_vram_match(self):
        with tempfile.TemporaryDirectory() as td:
            witness,native,pre,trace=setup(td)
            lines=trace.read_text().splitlines()
            item=json.loads(lines[-1]);item["words"][-1]^=1
            lines[-1]=json.dumps(item)
            trace.write_text("\n".join(lines)+"\n")
            with self.assertRaisesRegex(ValueError,"packet differs"):
                bind(witness,native,pre,trace)

    def test_native_vram_tampering_rejected_even_if_paused_witness_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            witness,native,pre,trace=setup(td)
            original=bytearray(pre.read_bytes());original[31]^=1
            pre.write_bytes(original)
            with self.assertRaises(ValueError):
                bind(witness,native,pre,trace)

    def test_partial_tail_rejected_and_explicit_override_is_not_same_frame_proof(self):
        with tempfile.TemporaryDirectory() as td:
            native_records=base_records()+[(GP0,[0])]
            witness,native,pre,trace=setup(td,native_records=native_records)
            with self.assertRaisesRegex(ValueError,"complete native capture"):
                bind(witness,native,pre,trace)
            report=bind(witness,native,pre,trace,
                        require_complete_native_capture=False)
            self.assertFalse(report["native_capture_whole_dump_vsync_end_verified"])
            self.assertTrue(report["interpretation"][
                "native_first_vsync_not_proven_same_as_paused_screenshot"])

    def test_an_otherwise_complete_second_native_frame_remains_first_frame_only(self):
        with tempfile.TemporaryDirectory() as td:
            frames=base_records()+[(GP0,[0]),(VSYNC,[5678,0])]
            witness,native,pre,trace=setup(td,native_records=frames)
            report=bind(witness,native,pre,trace,expected_completed_frames=2)
            self.assertEqual(report["native_completed_frame_count"],2)
            self.assertEqual(report["native_first_vsync_cycle_stamp"],1234)
            self.assertEqual(report["stage437_operator_frame_label"],449)

    def test_nonmonotonic_native_frame_sequence_fails_full_binding(self):
        with tempfile.TemporaryDirectory() as td:
            frames=base_records()+[(VSYNC,[1234,0])]
            witness,native,pre,trace=setup(td,native_records=frames)
            with self.assertRaisesRegex(ValueError,"NONMONOTONIC"):
                bind(witness,native,pre,trace)

    def test_expected_native_hash_game_serial_or_frame_rejected_independently(self):
        with tempfile.TemporaryDirectory() as td:
            witness,native,pre,trace=setup(td)
            for opts,part in [
                ({"expected_native_sha256":"f"*64},"independent SHA256"),
                ({"expected_native_game_id":"SLUS-00000"},"differs from caller"),
                ({"expected_frame":999},"frame differs"),
                ({"expected_completed_frames":3},"UNEXPECTED_COMPLETED_FRAME_COUNT"),
            ]:
                with self.subTest(opts=opts),self.assertRaisesRegex(ValueError,part):
                    bind(witness,native,pre,trace,**opts)

    def test_stage432_witness_changed_between_two_independent_checks(self):
        with tempfile.TemporaryDirectory() as td:
            witness,native,pre,trace=setup(td)
            from bind_private_screen_witness_to_gpudump import (
                verify_private_frame_witness as checker)
            counter=[0]
            def swapped(*args,**kwargs):
                report=checker(*args,**kwargs)
                counter[0]+=1
                if counter[0]==2:
                    report["screen_sha256"]="1"*64
                return report
            with patch("bind_private_screen_witness_to_gpudump.verify_private_frame_witness",
                       side_effect=swapped),self.assertRaisesRegex(ValueError,"changed during"):
                bind(witness,native,pre,trace)

    def test_witness_basename_validation_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as td:
            witness,native,pre,trace=setup(td)
            with self.assertRaises(ValueError):
                bind_private_screen_witness_to_gpu_dump(
                    witness,"../outside",native,pre,trace)

    def test_symlink_witness_directory_refused(self):
        with tempfile.TemporaryDirectory() as td:
            witness,native,pre,trace=setup(td)
            alias=Path(td)/"witness-link"
            alias.symlink_to(witness,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,"invalid private"):
                bind_private_screen_witness_to_gpu_dump(
                    alias,"surf",native,pre,trace)

    def test_strict_mode_requires_boolean_options(self):
        with tempfile.TemporaryDirectory() as td:
            witness,native,pre,trace=setup(td)
            for kw in (
                {"require_exact_vram_match":1},
                {"require_complete_native_capture":"yes"},
            ):
                with self.subTest(kw=kw),self.assertRaisesRegex(ValueError,"invalid strict"):
                    bind(witness,native,pre,trace,**kw)

    def test_metadata_omits_screenshot_pixels_gpu_words_and_disc_info(self):
        with tempfile.TemporaryDirectory() as td:
            witness,native,pre,trace=setup(td)
            report=bind(witness,native,pre,trace)
            encoded=json.dumps(report)
            for forbidden in (
                    '"raw_screenshot_png"','"raw_vram_u16"',
                    '"original_gp0_words"','"original_disc_info_json"',
                    '"original_clut_color_u16"','"original_map_geometry"'):
                self.assertNotIn(forbidden,encoded)
            self.assertTrue(report["interpretation"][
                "original_screenshot_pixels_vram_gp0_words_and_disc_info_not_emitted"])
            self.assertTrue(report["interpretation"][
                "all_hashes_and_witness_metadata_remain_owner_private"])


if __name__=="__main__":
    unittest.main()
