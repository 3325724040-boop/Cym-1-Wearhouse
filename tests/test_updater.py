import contextlib
import io
import os
from pathlib import Path
import sqlite3
import socket
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import updater


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / '艾霓 project'
        self.root.mkdir()
        self.stage = Path(self.temp.name) / 'stage'
        self.stage.mkdir()
        self.names = sorted(updater.REQUIRED | {'tests/test_example.py'})
        for name in self.names:
            path = self.stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('new content', encoding='utf-8')
        (self.root / 'app.py').write_text('old app', encoding='utf-8')
        (self.root / '饰品价目表.xlsx').write_bytes(b'original spreadsheet')
        (self.root / 'local-settings.json').write_text('user settings')
        (self.root / 'data' / 'images').mkdir(parents=True)
        (self.root / 'data' / 'images' / 'photo.jpg').write_bytes(b'private original photo')
        with sqlite3.connect(self.root / 'data' / 'warehouse.sqlite3') as db:
            db.execute('CREATE TABLE stock(quantity INTEGER)')
            db.execute('INSERT INTO stock VALUES(2000)')
        self.environment = patch.dict(os.environ)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        os.environ.pop('WAREHOUSE_DB', None)

    def assert_data(self, folder):
        with sqlite3.connect(folder / 'warehouse.sqlite3') as db:
            self.assertEqual(db.execute('SELECT quantity FROM stock').fetchone()[0], 2000)
        self.assertEqual((folder / 'images' / 'photo.jpg').read_bytes(), b'private original photo')

    def test_successful_install_backs_up_data_and_preserves_user_files(self):
        backup = updater.install(self.root, self.stage, self.names, 'a' * 40)
        self.assertEqual((self.root / 'app.py').read_text(), 'new content')
        self.assertEqual((backup / 'code' / 'app.py').read_text(), 'old app')
        self.assertEqual((self.root / '饰品价目表.xlsx').read_bytes(), b'original spreadsheet')
        self.assertEqual((self.root / 'local-settings.json').read_text(), 'user settings')
        self.assert_data(self.root / 'data')
        self.assert_data(backup / 'data')
        self.assertFalse((self.root / '.runtime' / 'pending-update.json').exists())

    def test_partial_install_error_restores_old_code_and_removes_new_files(self):
        original = updater.copy_atomic
        def fail(source, destination):
            if Path(source) == self.stage / 'storefront.py':
                raise OSError('simulated locked file')
            return original(source, destination)
        with patch.object(updater, 'copy_atomic', side_effect=fail):
            with self.assertRaisesRegex(updater.UpdateError, '已恢复旧代码'):
                updater.install(self.root, self.stage, self.names, 'a' * 40)
        self.assertEqual((self.root / 'app.py').read_text(), 'old app')
        self.assertFalse((self.root / 'launch.py').exists())
        self.assert_data(self.root / 'data')

    def test_backup_failure_prevents_code_replacement(self):
        with patch.object(updater.shutil, 'copytree', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                updater.install(self.root, self.stage, self.names, 'a' * 40)
        self.assertEqual((self.root / 'app.py').read_text(), 'old app')
        self.assert_data(self.root / 'data')

    def test_recovery_after_forced_termination_preserves_current_business_data(self):
        original = updater.copy_atomic
        def crash(source, destination):
            if Path(source) == self.stage / 'storefront.py':
                raise SystemExit('simulated process termination')
            return original(source, destination)
        with patch.object(updater, 'copy_atomic', side_effect=crash):
            with self.assertRaises(SystemExit):
                updater.install(self.root, self.stage, self.names, 'a' * 40)
        self.assertEqual((self.root / 'app.py').read_text(), 'new content')
        with contextlib.redirect_stdout(io.StringIO()):
            updater.recover_pending(self.root)
        self.assertEqual((self.root / 'app.py').read_text(), 'old app')
        self.assertFalse((self.root / 'launch.py').exists())
        self.assert_data(self.root / 'data')

    def test_lock_prevents_updating_while_app_is_running_and_releases(self):
        with updater.project_lock(self.root, ('admin',)):
            with self.assertRaises(updater.UpdateError):
                with updater.project_lock(self.root, ('update', 'admin', 'shop')):
                    self.fail('must not acquire running app lock')
        with updater.project_lock(self.root, ('update', 'admin', 'shop')):
            pass

    def test_legacy_running_service_blocks_updates_without_being_killed(self):
        with socket.socket() as server:
            server.bind(('127.0.0.1', 0)); server.listen()
            os.environ['PORT'] = str(server.getsockname()[1])
            with self.assertRaises(updater.UpdateError):
                updater.ensure_stopped()
            self.assertGreater(server.fileno(), -1)

    def archive(self, extra=None):
        path = Path(self.temp.name) / 'release.zip'
        with zipfile.ZipFile(path, 'w') as package:
            for name in self.names:
                package.writestr('release/' + name, 'content')
            for name, value in (extra or {}).items():
                package.writestr(name, value)
        return path

    def test_archive_protects_data_spreadsheet_and_stable_bat(self):
        archive = self.archive({'release/data/warehouse.sqlite3': 'evil',
                                'release/饰品价目表.xlsx': 'replacement',
                                'release/update-windows.bat': 'replace running bootstrap'})
        names = updater.unpack(archive, self.stage, expected_root='release')
        self.assertNotIn('data/warehouse.sqlite3', names)
        self.assertNotIn('饰品价目表.xlsx', names)
        self.assertNotIn('update-windows.bat', names)
        self.assertFalse((self.stage / 'data').exists())

    def test_archive_rejects_traversal_wrong_version_and_missing_files(self):
        with self.assertRaises(updater.UpdateError):
            updater.unpack(self.archive({'release/../../outside.py': 'bad'}), self.stage)
        with self.assertRaises(updater.UpdateError):
            updater.unpack(self.archive(), self.stage, expected_root='wrong-commit')
        with zipfile.ZipFile(Path(self.temp.name) / 'empty.zip', 'w'):
            pass
        with self.assertRaises(updater.UpdateError):
            updater.unpack(Path(self.temp.name) / 'empty.zip', self.stage)

    def test_https_hosts_and_latest_commit_validation(self):
        for url in ['http://github.com/x', 'https://example.com/x', 'https://user:pass@github.com/x', 'https://github.com:444/x']:
            with self.assertRaises(updater.UpdateError):
                updater.allowed_url(url)
        commit = 'b' * 40
        feed = ('<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>tag:github.com,2008:Grit::Commit/' + commit + '</id></entry></feed>').encode()
        with patch.object(updater, 'fetch', return_value=feed):
            self.assertEqual(updater.latest_commit(), commit)
        with patch.object(updater, 'fetch', return_value=b'<feed/>'):
            with self.assertRaises(updater.UpdateError):
                updater.latest_commit()

    def test_custom_database_and_symlink_are_not_silently_modified(self):
        os.environ['WAREHOUSE_DB'] = str(Path(self.temp.name) / 'external.sqlite3')
        with self.assertRaisesRegex(updater.UpdateError, '自定义数据库'):
            updater.preflight(self.root, self.names)
        os.environ.pop('WAREHOUSE_DB')
        if os.name != 'nt':
            (self.root / 'static').symlink_to(self.stage / 'static', target_is_directory=True)
            with self.assertRaises(updater.UpdateError):
                updater.preflight(self.root, self.names)

    def test_stage_validation_rejects_failed_tests_and_zero_test_runs(self):
        tests = self.stage / 'tests'; tests.mkdir(exist_ok=True)
        case = tests / 'test_example.py'
        case.write_text('import unittest\nclass Broken(unittest.TestCase):\n def test_failure(self): self.fail("broken release")\n')
        with self.assertRaisesRegex(updater.UpdateError, '自检未通过'):
            updater.validate_stage(self.stage, ['tests/test_example.py'])
        case.write_text('# zero tests must not validate a release\n')
        with self.assertRaisesRegex(updater.UpdateError, '自检未通过'):
            updater.validate_stage(self.stage, ['tests/test_example.py'])
