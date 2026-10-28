"""Transactional updater for the user-owned GitHub project. Python standard library only."""
import contextlib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

REPOSITORY = '3325724040-boop/Cym-1-Wearhouse'
TRUSTED_HOSTS = {'github.com', 'codeload.github.com'}
MAX_DOWNLOAD = 50 * 1024 * 1024
MAX_EXPANDED = 100 * 1024 * 1024
REQUIRED = {'app.py', 'launch.py', 'updater.py', 'start-windows.bat',
            'static/index.html', 'static/app.js', 'static/gallery.js', 'static/style.css'}
OBSOLETE = {'storefront.py', 'static/shop.html', 'static/shop.js', 'static/shop.css',
            'tests/test_storefront.py'}
ROOT_FILES = REQUIRED | {'README.md', 'Windows使用说明.txt'}


class UpdateError(Exception):
    pass


@contextlib.contextmanager
def project_lock(root, roles):
    """Cooperative process locks, released by the OS even after an interrupted process."""
    folder = Path(root) / '.runtime'
    reject_links(folder)
    folder.mkdir(exist_ok=True)
    handles = []
    try:
        for role in roles:
            reject_links(folder / (role + '.lock'))
            file = open(folder / (role + '.lock'), 'a+b')
            handles.append(file)
            file.seek(0, 2)
            if not file.tell():
                file.write(b'0'); file.flush()
            file.seek(0)
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise UpdateError('程序或更新器仍在运行。请关闭原来的黑色运行窗口后重试。')
        yield
    finally:
        for file in reversed(handles):
            file.close()


def ensure_stopped():
    for port in {8000, 8001, int(os.environ.get('PORT', '8000'))}:
        with socket.socket() as probe:
            probe.settimeout(0.5)
            if probe.connect_ex(('127.0.0.1', port)) == 0:
                raise UpdateError(f'端口 {port} 仍在使用。请先关闭原来的黑色运行窗口，再双击更新。不会强制结束其他程序。')


def allowed_url(url):
    from urllib.parse import urlsplit
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in TRUSTED_HOSTS or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise UpdateError('下载地址不属于受信任的 GitHub HTTPS 地址')


class GitHubRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        allowed_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, limit):
    allowed_url(url)
    req = urllib.request.Request(url, headers={'User-Agent': 'Aini-Warehouse-Updater/1.0'})
    # Uses the OS/Python trust store. Never disables TLS certificate verification.
    opener = urllib.request.build_opener(GitHubRedirect())
    with opener.open(req, timeout=30) as response:
        content = response.read(limit + 1)
    if len(content) > limit:
        raise UpdateError('下载内容超出允许大小')
    return content


def latest_commit():
    feed = ET.fromstring(fetch(f'https://github.com/{REPOSITORY}/commits/main.atom', 1024 * 1024))
    entry = feed.findtext('{http://www.w3.org/2005/Atom}entry/{http://www.w3.org/2005/Atom}id', '')
    commit = entry.rsplit('/', 1)[-1]
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise UpdateError('GitHub 返回的版本号无效')
    return commit


def managed(name):
    # Never install data, photos, the user's spreadsheet, .git, settings or unknown files.
    # The stable running BAT bootstrap is deliberately not replaced while CMD is reading it.
    return name in ROOT_FILES or bool(re.fullmatch(r'[a-z_][a-z0-9_]*\.py', name)) or bool(re.fullmatch(r'static/[A-Za-z0-9_-]+\.(?:js|css|html)', name)) or bool(re.fullmatch(r'tests/(?:test_[A-Za-z0-9_]+|browser_gallery_smoke)\.py', name))


def unpack(archive, stage, expected_root=None):
    selected = []
    seen = set()
    top = None
    total = 0
    with zipfile.ZipFile(archive) as package:
        if len(package.infolist()) > 2000:
            raise UpdateError('压缩包包含过多文件')
        for entry in package.infolist():
            path = PurePosixPath(entry.filename)
            if path.is_absolute() or '\\' in entry.filename or any(p in ('..', '.') or ':' in p for p in path.parts):
                raise UpdateError('压缩包含有不安全路径')
            if not path.parts or stat.S_ISLNK(entry.external_attr >> 16):
                raise UpdateError('压缩包含有不安全文件')
            if top is None:
                top = path.parts[0]
                if expected_root and top != expected_root:
                    raise UpdateError('压缩包与所选版本不匹配')
            if path.parts[0] != top:
                raise UpdateError('压缩包目录格式不正确')
            total += entry.file_size
            if total > MAX_EXPANDED:
                raise UpdateError('解压内容超出允许大小')
            if entry.is_dir():
                continue
            name = '/'.join(path.parts[1:])
            if not managed(name):
                continue
            if name.casefold() in seen:
                raise UpdateError('压缩包含有重复文件')
            seen.add(name.casefold())
            destination = stage / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(package.read(entry))  # ZIP CRC verification is preserved.
            selected.append(name)
    if not REQUIRED.issubset(selected) or not any(n.startswith('tests/test_') for n in selected):
        raise UpdateError('新版缺少必要程序或测试文件，未修改当前程序')
    return sorted(selected)


def reject_links(path):
    path = Path(path)
    if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
        raise UpdateError('更新目录包含链接，请先使用普通文件夹备份并更新')


def preflight(root, names):
    reject_links(root)
    for name in names:
        target = root / name
        for part in [target, *target.parents]:
            if part == root.parent:
                break
            reject_links(part)
        if target.exists() and not target.is_file():
            raise UpdateError(f'{name} 不是普通文件，未更新')
    data = root / 'data'
    reject_links(data)
    if data.exists():
        for folder, directories, files in os.walk(data, followlinks=False):
            for name in directories + files:
                reject_links(Path(folder) / name)
    configured = os.environ.get('WAREHOUSE_DB')
    if configured and Path(configured).resolve() != (data / 'warehouse.sqlite3').resolve():
        raise UpdateError('检测到自定义数据库路径，请先单独备份数据库和图片，并使用手动更新。当前数据未修改。')


def validate_stage(stage, names):
    for name in names:
        if name.endswith('.py'):
            compile((stage / name).read_bytes(), name, 'exec')
    settings = os.environ.copy()
    settings.pop('WAREHOUSE_DB', None)
    settings.pop('PYTHONPATH', None)
    settings['PYTHONIOENCODING'] = 'utf-8'
    result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
                            cwd=stage, env=settings, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding='utf-8', errors='replace', timeout=180)
    (stage / 'validation.log').write_text(result.stdout, encoding='utf-8')
    if result.returncode != 0 or not re.search(r'Ran [1-9][0-9]* tests?\b', result.stdout):
        raise UpdateError('新版自检未通过，未修改当前程序。\n' + result.stdout[-2000:])


def copy_atomic(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.update-', delete=False) as file:
            temp_name = file.name
            with open(source, 'rb') as original:
                shutil.copyfileobj(original, file)
        os.replace(temp_name, target)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)


def install(root, stage, names, commit):
    """Back up before modifying managed code; business data is never replaced."""
    managed_names = sorted(set(names) | OBSOLETE)
    preflight(root, managed_names)
    backups = root.parent / (root.name + '-backups')
    reject_links(backups)
    backups.mkdir(exist_ok=True)
    backup = backups / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup.mkdir()
    existing = []
    # Complete backup must succeed before the first code file is touched.
    if (root / 'data').exists():
        shutil.copytree(root / 'data', backup / 'data')
    for name in managed_names:
        if (root / name).exists():
            destination = backup / 'code' / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / name, destination)
            existing.append(name)
    manifest = {'commit': commit, 'existing': existing, 'managed': managed_names, 'backup': str(backup.resolve()),
                'hashes': {name: hashlib.sha256((backup / 'code' / name).read_bytes()).hexdigest() for name in existing}}
    (backup / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    runtime = root / '.runtime'; runtime.mkdir(exist_ok=True)
    pending = runtime / 'pending-update.json'
    copy_atomic(backup / 'manifest.json', pending)
    changed = []
    try:
        for name in managed_names:
            if name in names:
                copy_atomic(stage / name, root / name)
            else:
                (root / name).unlink(missing_ok=True)
            changed.append(name)
    except (Exception, KeyboardInterrupt) as error:
        failures = []
        for name in reversed(changed):
            try:
                if name in existing:
                    copy_atomic(backup / 'code' / name, root / name)
                else:
                    (root / name).unlink(missing_ok=True)
            except OSError:
                failures.append(name)
        if failures:
            raise UpdateError(f'更新中断，部分代码需从备份恢复：{failures}。备份：{backup}') from error
        pending.unlink()
        raise UpdateError(f'更新未完成，已恢复旧代码，库存未替换。备份：{backup}') from error
    pending.unlink()
    return backup


def recover_pending(root):
    """Recover code after power loss or forced process termination; never restore over business data."""
    pending = root / '.runtime' / 'pending-update.json'
    if not pending.exists():
        return
    manifest = json.loads(pending.read_text(encoding='utf-8'))
    backup = Path(manifest['backup']).resolve()
    expected_parent = (root.parent / (root.name + '-backups')).resolve()
    if backup.parent != expected_parent:
        raise UpdateError('上次更新的恢复记录异常，请保留备份并手动检查')
    names, existing = manifest['managed'], manifest['existing']
    if not all(isinstance(n, str) and managed(n) for n in names) or not set(existing).issubset(names):
        raise UpdateError('上次更新的恢复文件列表异常')
    preflight(root, names)
    for name in existing:
        source = backup / 'code' / name
        if hashlib.sha256(source.read_bytes()).hexdigest() != manifest['hashes'][name]:
            raise UpdateError('备份代码校验失败，停止自动恢复，请保留备份')
    for name in names:
        if name in existing:
            copy_atomic(backup / 'code' / name, root / name)
        else:
            (root / name).unlink(missing_ok=True)
    pending.unlink()
    print('Recovered the previous code after an interrupted update. Data unchanged.', flush=True)


def main():
    root = Path(__file__).resolve().parent
    try:
        with project_lock(root, ('update', 'admin', 'shop')):
            ensure_stopped()
            recover_pending(root)
            print('Checking GitHub for the latest version...', flush=True)
            commit = latest_commit()
            with tempfile.TemporaryDirectory(prefix='aini-update-') as folder:
                work = Path(folder)
                archive = work / 'release.zip'
                archive.write_bytes(fetch(f'https://github.com/{REPOSITORY}/archive/{commit}.zip', MAX_DOWNLOAD))
                stage = work / 'stage'; stage.mkdir()
                names = unpack(archive, stage, 'Cym-1-Wearhouse-' + commit)
                print(f'Version: {commit[:12]}. Checking downloaded code...', flush=True)
                validate_stage(stage, names)
                preflight(root, names)
                if (all((root / name).is_file() and hashlib.sha256((root / name).read_bytes()).digest() == hashlib.sha256((stage / name).read_bytes()).digest() for name in names)
                        and not any((root / name).exists() for name in OBSOLETE)):
                    print('Already up to date. Data unchanged.', flush=True)
                    return 0
                print('Backing up inventory, photos and existing code...', flush=True)
                backup = install(root, stage, names, commit)
                print(f'Update complete. Backup: {backup}', flush=True)
                print('Starting the app next. Use Ctrl+F5 in the browser if needed.', flush=True)
        return 0
    except KeyboardInterrupt:
        print('Update cancelled. If file installation had started, see the backup folder.')
        return 1
    except Exception as error:
        print(f'Update failed: {error}')
        print('Do not delete your data folder. Close running app windows and retry after checking the message above.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
