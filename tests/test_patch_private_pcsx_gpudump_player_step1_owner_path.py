"""Stage519 opt-in owner-only direct path GUI Player Frame-1 V2 patch tests.

Pure source transformations only. No game images or private binary artifacts.
"""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from patch_private_pcsx_gpudump_player_step1_owner_path import (
    ENV_NAME,BUTTON_ANCHOR,DIRECT_BODY,add_direct_path_to_patched_gui,
    check_or_apply,
)

FRAGMENT='#include <cstdio>\n' + BUTTON_ANCHOR

class Stage519PrivateGUIPathTests(unittest.TestCase):
    def test_direct_path_is_strict_opt_in_and_preserves_gui_fallback(self):
        transformed=add_direct_path_to_patched_gui(FRAGMENT)
        self.assertIn('#include <cstdlib>\n',transformed)
        self.assertIn('std::getenv("'+ENV_NAME+'")',transformed)
        self.assertIn('} else {\n                m_stepExportDialog.openDialog();',transformed)
        self.assertEqual(transformed.count('m_stepExportDialog.openDialog();'),1)
        self.assertNotIn('std::getenv("'+ENV_NAME+'")',FRAGMENT)

    def test_destination_must_be_absolute_and_parent_directory_exists(self):
        transformed=add_direct_path_to_patched_gui(FRAGMENT)
        for check in ('requested.is_absolute()','requested.filename().empty()',
                      'std::filesystem::is_directory(parent, parentError)',
                      'std::filesystem::is_symlink(parent, parentError)'):
            with self.subTest(check=check):
                self.assertIn(check,transformed)

    def test_writer_is_exact_version_two_snapshot_and_clears_frozen_data(self):
        self.assertIn('m_frozenDumpSHA256',DIRECT_BODY)
        self.assertIn('m_frozenStepOneVRAM,',DIRECT_BODY)
        self.assertIn('m_frozenStepOneFrame',DIRECT_BODY)
        self.assertIn('m_frozenStepOneVRAM.clear();',DIRECT_BODY)
        self.assertIn('m_frozenDumpSHA256.fill(0);',DIRECT_BODY)
        self.assertNotIn('fwrite',DIRECT_BODY)

    def test_missing_or_duplicated_button_anchor_refused(self):
        for malformed in ('#include <cstdio>\n',FRAGMENT+BUTTON_ANCHOR):
            with self.subTest(malformed=malformed[:32]):
                with self.assertRaisesRegex(ValueError,'anchor missing or duplicated'):
                    add_direct_path_to_patched_gui(malformed)

    def test_missing_or_duplicated_cstdio_anchor_refused(self):
        for malformed in (BUTTON_ANCHOR,
                          '#include <cstdio>\n#include <cstdio>\n'+BUTTON_ANCHOR):
            with self.subTest(malformed=malformed[:32]):
                with self.assertRaisesRegex(ValueError,'anchor missing or duplicated'):
                    add_direct_path_to_patched_gui(malformed)

    def test_unpinned_or_missing_checkout_does_not_produce_patch(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError,'checkout is absent'):
                check_or_apply(Path(root)/'missing')
            with self.assertRaises(Exception):
                check_or_apply(root)

if __name__=="__main__":
    unittest.main()
