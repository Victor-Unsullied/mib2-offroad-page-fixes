from hashlib import sha256
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock
from contextlib import redirect_stderr, redirect_stdout

import install


class TemperatureInstallerTests(TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.state = Path(self.folder.name) / 'state'
        self.state.mkdir()

    def test_verified_download_is_cached_for_offline_use(self):
        artifact = b'verified test archive'
        with (mock.patch.object(install, 'SPORT_SHA256', sha256(artifact).hexdigest()),
              mock.patch.object(install, 'urlopen', return_value=BytesIO(artifact)) as download,
              redirect_stdout(StringIO())):
            self.assertEqual(install.prepare_archive(self.state), artifact)
            self.assertEqual(install.prepare_archive(self.state), artifact)
        download.assert_called_once_with(install.SPORT_ARCHIVE, timeout=25)

    def test_corrupt_download_is_never_cached(self):
        with (mock.patch.object(install, 'urlopen', return_value=BytesIO(b'corrupt')),
              redirect_stdout(StringIO()),
              self.assertRaisesRegex(ValueError, 'failed verification')):
            install.prepare_archive(self.state)
        self.assertFalse((self.state / 'sports.zip').exists())

    def test_corrupt_cache_cannot_run_the_engine(self):
        (self.state / 'sports.zip').write_bytes(b'corrupt')
        with (mock.patch.object(install, 'STATE', self.state),
              mock.patch.object(install.subprocess, 'run') as run,
              redirect_stderr(StringIO())):
            self.assertEqual(install.main(['--check']), 1)
        run.assert_not_called()

    def test_rollback_after_inspection_only_stops_before_download(self):
        (self.state / 'sports.zip').touch()
        (self.state / 'native' / 'logs').mkdir(parents=True)
        with (mock.patch.object(install, 'STATE', self.state),
              mock.patch.object(install.sys, 'platform', 'win32'),
              mock.patch.object(install, 'urlopen') as download,
              redirect_stderr(StringIO()),
              self.assertRaises(SystemExit) as error):
            install.main(['--rollback'])
        self.assertEqual(error.exception.code, 2)
        download.assert_not_called()
