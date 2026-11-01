"""Tests for scripts/leak_check.py. Run: python3 -I -m unittest discover -s tests

Banned words are built from fragments so this file passes the check it tests.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "scripts", "leak_check.py")
sys.path.insert(0, os.path.dirname(SCRIPT))
import leak_check  # noqa: E402

PRODUCT = "J" + "ev"
PROVIDER = "Type" + "Safe"


class TreeCase(unittest.TestCase):
    def tree(self, files):
        d = tempfile.mkdtemp(prefix="leak-test-")
        self.addCleanup(shutil.rmtree, d, True)
        subprocess.run(["git", "init", "-q", d], check=True)
        for rel, text in files.items():
            p = os.path.join(d, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(text)
        subprocess.run(["git", "-C", d, "add", "-A"], check=True)
        return d

    def run_check(self, root):
        return subprocess.run([sys.executable, "-I", SCRIPT, "--root", root], capture_output=True, text=True)

    def test_clean_tree_passes(self):
        r = self.run_check(self.tree({"README.md": "A synthetic benchmark.\n", "a.py": "x = 1\n"}))
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("0 hits", r.stdout)

    def test_each_plain_term_fails(self):
        for text, what in [("see /" + "Users/someone/x\n", "macOS home directory"),
                           ("my lap" + "top\n", "portable computer"),
                           ("see decision" + "-log.md\n", "internal log file"),
                           ("in the scratch" + "pad\n", "scratch directory"),
                           ("RELEASE_" + "VERIFY.md has it\n", "internal verify file")]:
            r = self.run_check(self.tree({"doc.md": text}))
            self.assertEqual(r.returncode, 1, text)
            self.assertIn("doc.md:1: " + what, r.stdout)

    def test_hashed_names_fail_in_prose(self):
        r = self.run_check(self.tree({"doc.md": "Judged by %s %s.\n" % (PROVIDER, PRODUCT)}))
        self.assertEqual(r.returncode, 1)
        self.assertIn("doc.md:1: provider name", r.stdout)
        self.assertIn("doc.md:1: provider product name", r.stdout)

    def test_internal_files_fail_by_name(self):
        for rel in ("RELEASE_" + "VERIFY.md", "docs/PAPER_" + "VERIFY.md", "notes.md", "dev-handoff.txt"):
            r = self.run_check(self.tree({rel: "fine text\n"}))
            self.assertEqual(r.returncode, 1, rel)
            self.assertIn(rel + ":0: internal file is tracked", r.stdout)

    def test_code_identifier_allowlist(self):
        code = 'os.environ.pop("NO_QUIT_%s")\nnq.%s = None\n' % (PRODUCT.upper(), PRODUCT.lower())
        self.assertEqual(self.run_check(self.tree({"s.py": code})).returncode, 0)
        # The same lowercase identifier in prose fails, and the capitalized name fails even in code.
        self.assertEqual(self.run_check(self.tree({"s.md": "nq.%s\n" % PRODUCT.lower()})).returncode, 1)
        self.assertEqual(self.run_check(self.tree({"s.py": "# uses %s\n" % PRODUCT})).returncode, 1)

    def test_cli_forms_allowed_anywhere(self):
        text = "Run `realstop judge %s` or pass `--judge %s`.\n" % (PRODUCT.lower(), PRODUCT.lower())
        self.assertEqual(self.run_check(self.tree({"README.md": text})).returncode, 0)

    def test_untracked_files_are_ignored(self):
        d = self.tree({"README.md": "ok\n"})
        with open(os.path.join(d, "notes.md"), "w") as f:
            f.write("my lap" + "top\n")
        self.assertEqual(self.run_check(d).returncode, 0)

    def test_not_a_git_tree_exits_2(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        self.assertEqual(self.run_check(d).returncode, 2)

    def test_hash_matching_on_tokens(self):
        h = {leak_check._h("zq-" + "xterm"): "planted", leak_check._h("plant" + "@example.org"): "email"}
        self.assertEqual(leak_check.scan_line("a.md", "use zq-xterm now", h), ["planted"])
        self.assertEqual(leak_check.scan_line("a.md", "mail plant@example.org", h), ["email"])
        self.assertEqual(leak_check.scan_line("a.md", "zqxterm label", h), [])


if __name__ == "__main__":
    unittest.main()
