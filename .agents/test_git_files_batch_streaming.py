"""Bounded Git blob streaming at the acquisition snapshot boundary."""
import hashlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_evidence_dag_journeys import z


class TrackedStream(io.BytesIO):
    largest_read = 0

    def read(self, size=-1):
        self.largest_read = max(self.largest_read, size)
        return super().read(size)


class RecordingInput(io.BytesIO):
    def close(self):
        self.written = self.getvalue()
        super().close()


class BatchProcess:
    def __init__(self, reply, returncode=0):
        self.stdin = RecordingInput()
        self.stdout = TrackedStream(reply)
        self.returncode = returncode
        self.killed = False
        self.reaped = False

    def poll(self):
        return self.returncode if self.reaped else None

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self):
        self.reaped = True
        return self.returncode


class GitFilesBatchStreamingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name)
        def git(*args):
            return subprocess.check_output(['git', *args], cwd=self.repo)
        git('init', '-q')
        git('config', 'user.name', 'Probe')
        git('config', 'user.email', 'probe@example.com')
        (self.repo / 'one.txt').write_bytes(b'content')
        git('add', 'one.txt')
        git('commit', '-qm', 'test: one blob')
        self.commit = git('rev-parse', 'HEAD').decode().strip()
        self.oid = git('rev-parse', 'HEAD:one.txt').strip()
        self.tree = git('ls-tree', '-rz', '--full-tree', self.commit)
        self.workflow = object.__new__(z._workflow.Workflow)
        self.workflow.repo = self.repo
        self.workflow._git_snapshots = {}

    def observe(self, reply, returncode=0):
        process = BatchProcess(reply, returncode)
        with mock.patch.object(z._workflow.subprocess, 'run',
                               return_value=subprocess.CompletedProcess([], 0, self.tree)), \
             mock.patch.object(z._workflow.subprocess, 'Popen', return_value=process) as popen:
            return process, popen, self.workflow.git_files(self.commit)

    def test_exact_frame_hashes_in_chunks_and_reaps_process(self):
        content = b'x' * (2 * 1024 * 1024)
        reply = self.oid + b' blob ' + str(len(content)).encode() + b'\n' + content + b'\n'
        process, popen, mapping = self.observe(reply)
        self.assertEqual({'one.txt': 'sha256:' + hashlib.sha256(content).hexdigest()}, mapping)
        self.assertLessEqual(process.stdout.largest_read, 65536)
        self.assertEqual(self.oid + b'\n', process.stdin.written)
        self.assertTrue(process.reaped)
        self.assertFalse(process.killed)
        self.assertEqual(1, popen.call_count)

    def test_tree_paths_duplicates_symlinks_and_internal_exclusion(self):
        (self.repo / 'same\nname').write_bytes(b'content')
        (self.repo / 'link').symlink_to('one.txt')
        (self.repo / '.zzzops').mkdir()
        (self.repo / '.zzzops' / 'hidden').write_bytes(b'hidden')
        subprocess.run(['git', 'add', '-A'], cwd=self.repo, check=True)
        subprocess.run(['git', 'commit', '-qm', 'test: special paths'], cwd=self.repo, check=True)
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=self.repo,
                                         text=True).strip()
        mapping = self.workflow.git_files(commit)
        self.assertEqual({'one.txt', 'same\nname', 'link'}, set(mapping))
        self.assertEqual(mapping['one.txt'], mapping['same\nname'])
        self.assertEqual('sha256:' + hashlib.sha256(b'one.txt').hexdigest(), mapping['link'])

    def test_malformed_frames_and_failed_process_never_cache_partial_mapping(self):
        good = self.oid + b' blob 7\ncontent\n'
        for reply, code in ((b'', 0), (b'junk\n', 0),
                            (b'0' * 40 + b' blob 7\ncontent\n', 0),
                            (self.oid + b' tree 7\ncontent\n', 0),
                            (self.oid + b' blob 7\nshort\n', 0),
                            (self.oid + b' blob 7\ncontent!', 0),
                            (good + b'trailing', 0)):
            with self.subTest(reply=reply[:60], code=code):
                process = BatchProcess(reply, code)
                with mock.patch.object(z._workflow.subprocess, 'run',
                                       return_value=subprocess.CompletedProcess([], 0, self.tree)), \
                     mock.patch.object(z._workflow.subprocess, 'Popen', return_value=process):
                    with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                        self.workflow.git_files(self.commit)
                self.assertTrue(process.reaped)
                self.assertTrue(process.killed)
                self.assertNotIn(self.commit, self.workflow._git_snapshots)

    def test_git_failure_raises_called_process_error_without_caching(self):
        reply = self.oid + b' blob 7\ncontent\n'
        process = BatchProcess(reply, 2)
        def fail_with_stderr(*_args, **kwargs):
            kwargs['stderr'].write(b'failure' * 20000)
            return process
        with mock.patch.object(z._workflow.subprocess, 'run',
                               return_value=subprocess.CompletedProcess([], 0, self.tree)), \
             mock.patch.object(z._workflow.subprocess, 'Popen', side_effect=fail_with_stderr):
            with self.assertRaises(subprocess.CalledProcessError) as raised:
                self.workflow.git_files(self.commit)
        self.assertEqual(2, raised.exception.returncode)
        self.assertEqual(65536, len(raised.exception.stderr))
        self.assertTrue(process.reaped)
        self.assertNotIn(self.commit, self.workflow._git_snapshots)
