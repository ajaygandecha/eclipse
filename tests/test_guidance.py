from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from pycparser import c_parser

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from guided_se import find_risky_functions, write_guidance_file


class GuidanceAnalysisTests(unittest.TestCase):
    def test_finds_dangerous_calls_array_writes_and_pointer_writes(self) -> None:
        ast = c_parser.CParser().parse(
            """
            void log_status(const char *msg) {
                puts(msg);
            }

            void parse_packet(char *input) {
                char buf[16];
                strcpy(buf, input);
            }

            void copy_bytes(char *src, int idx) {
                char arr[8];
                arr[idx] = src[0];
            }

            void write_offset(char *base, int offset) {
                char *cursor = base + offset;
                *cursor = 'A';
            }
            """
        )

        guidance = find_risky_functions(ast)

        self.assertEqual(
            guidance.risky_functions,
            ("parse_packet", "copy_bytes", "write_offset"),
        )
        self.assertEqual(
            guidance.notes["parse_packet"],
            ("calls dangerous API 'strcpy'",),
        )
        self.assertEqual(
            guidance.notes["copy_bytes"],
            ("contains non-constant array index write",),
        )
        self.assertEqual(
            guidance.notes["write_offset"],
            ("writes through pointer derived from pointer arithmetic",),
        )

    def test_writes_expected_json_payload(self) -> None:
        ast = c_parser.CParser().parse(
            """
            void parse_packet(char *input) {
                char buf[16];
                strcpy(buf, input);
            }
            """
        )
        guidance = find_risky_functions(ast)

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "risk.json"
            write_guidance_file(output_path, guidance)
            payload = json.loads(output_path.read_text())

        self.assertEqual(payload["analysis_version"], 1)
        self.assertEqual(payload["risky_functions"], ["parse_packet"])
        self.assertEqual(
            payload["notes"],
            {"parse_packet": ["calls dangerous API 'strcpy'"]},
        )


if __name__ == "__main__":
    unittest.main()
