import subprocess


def test_node_clean_strips_controls_and_normalizes_punctuation():
    script = """
      import assert from 'node:assert/strict';
      import { clean } from './src/node/sanitize.js';
      const dirty = "\\u200bI\\u2019m\\u0007 ready\\u2014really\\u2026\\n\\n\\nNext\\u201d";
      assert.equal(clean(dirty), "I'm ready - really...\\n\\nNext\\\"");
    """
    subprocess.run(["node", "--input-type=module", "-e", script], check=True)
