"""Run the actual C++ GTE model process to check strict input boundaries."""
import subprocess
import sys
import unittest

RUNNER = sys.argv.pop(1) if len(sys.argv) > 1 else None


class RunnerInputContract(unittest.TestCase):
    def run_input(self, values):
        self.assertIsNotNone(RUNNER)
        return subprocess.run([RUNNER], input=' '.join(map(str, values)) + '\n',
                              capture_output=True, text=True, timeout=5)

    def valid(self):
        inputs = [0] * 22
        inputs[0] = inputs[4] = inputs[8] = 4096
        inputs[14] = 200
        inputs[15] = 100
        inputs[20] = 1
        return inputs

    def test_ordinary_point(self):
        result = self.run_input(self.valid())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.split()), 11)

    def test_boundary_register_values(self):
        data = self.valid()
        data[0] = -32768
        data[9] = -2147483648
        data[12] = 32767
        data[15] = 65535
        data[16] = 2147483647
        data[18] = -32768
        data[19] = -2147483648
        data[21] = 1
        self.assertEqual(self.run_input(data).returncode, 0)

    def test_16bit_narrowing_rejected(self):
        data = self.valid()
        data[0] = 65536
        self.assertEqual(self.run_input(data).returncode, 2)

    def test_32bit_narrowing_rejected(self):
        data = self.valid()
        data[9] = 4294967296
        self.assertEqual(self.run_input(data).returncode, 2)

    def test_negative_h_rejected(self):
        data = self.valid()
        data[15] = -1
        self.assertEqual(self.run_input(data).returncode, 2)

    def test_invalid_sf_lm_rejected(self):
        for index in (20, 21):
            data = self.valid()
            data[index] = 2
            self.assertEqual(self.run_input(data).returncode, 2)

    def test_missing_input_rejected(self):
        self.assertEqual(self.run_input(self.valid()[:21]).returncode, 2)

    def test_extra_input_rejected(self):
        self.assertEqual(self.run_input(self.valid() + [1]).returncode, 2)

    def test_trailing_junk_rejected(self):
        result = self.run_input(self.valid())
        self.assertEqual(result.returncode, 0)
        broken = subprocess.run([RUNNER], input=' '.join(map(str, self.valid())) + ' garbage',
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(broken.returncode, 2)

    def test_excessive_decimal_rejected(self):
        data = self.valid()
        data[3] = int('9' * 30)
        self.assertEqual(self.run_input(data).returncode, 2)


if __name__ == '__main__':
    unittest.main()
