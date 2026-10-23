"""Bounded, data-only ZIP exchange. Native sketches are never opened here."""
import errno
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import unicodedata
import zipfile

MAX_MEMBERS = 4096
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
CHUNK_BYTES = 64 * 1024


def _member_name(name):
    if (not isinstance(name, str) or not name or '\\' in name or ':' in name
            or '\x00' in name or name.startswith('/')
            or any(part in ('', '.', '..') for part in name.split('/'))):
        raise ValueError(f"Unsafe archive path: {name!r}.")
    return unicodedata.normalize('NFC', name).casefold()


def _catalog(manager, data, root):
    from freecad.maxproframe.section_library import resolve_and_validate_asset_path
    manager._validate_folder_catalog_data(data)
    if not isinstance(data.get('_metadata'), dict) or not data['_metadata'].get('name'):
        raise ValueError('Catalog requires named metadata.')
    assets = {}
    # Reject local source paths at any nesting level rather than leaking them.
    def validate_value(value):
        if isinstance(value, dict):
            for child in value.values():
                validate_value(child)
        elif isinstance(value, list):
            for child in value:
                validate_value(child)
        elif isinstance(value, str):
            if value.startswith(('/', '\\')) or re.match(r'^[A-Za-z]:', value):
                raise ValueError('Catalog contains an absolute local path.')
        elif isinstance(value, float) and not math.isfinite(value):
            raise ValueError('Catalog contains a non-finite number.')
    validate_value(data)
    for family, props in data.items():
        if family.startswith('_'):
            continue
        sizes = props.get('sizes', {})
        if not isinstance(sizes, dict):
            raise ValueError(f"Family '{family}' sizes must be a dictionary.")
        for size, values in sizes.items():
            if not isinstance(values, dict):
                raise ValueError(f"Size '{size}' must be a dictionary.")
            if 'asset_path' in values:
                relative = values['asset_path']
                _member_name(relative)
                resolved = resolve_and_validate_asset_path(str(root), relative)
                if not relative.lower().endswith('.fcstd'):
                    raise ValueError('Section assets must be FCStd files.')
                assets[relative] = resolved
    names = [_member_name(name) for name in assets]
    if len(set(names)) != len(names):
        raise ValueError('Conflicting asset names.')
    return assets


def _index(archive):
    infos = archive.infolist()
    if len(infos) > MAX_MEMBERS:
        raise ValueError('Archive member count exceeds limit.')
    names = {}
    total = 0
    for info in infos:
        key = _member_name(info.filename)
        mode = stat.S_IFMT(info.external_attr >> 16)
        if (info.orig_filename != info.filename or key in names
                or mode not in (0, stat.S_IFREG) or info.is_dir()
                or info.flag_bits & 1
                or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
            raise ValueError('Duplicate, special, encrypted or unsupported ZIP member.')
        if info.file_size > MAX_MEMBER_BYTES:
            raise ValueError('Archive member expanded size exceeds limit.')
        total += info.file_size
        if total > MAX_EXPANDED_BYTES:
            raise ValueError('Archive expanded size exceeds limit.')
        names[key] = info
    return {info.filename: info for info in names.values()}


def _stream(source, target, total, member_limit=None, total_limit=None):
    count = 0
    while True:
        chunk = source.read(CHUNK_BYTES)
        if not chunk:
            break
        count += len(chunk)
        total[0] += len(chunk)
        if (count > (MAX_MEMBER_BYTES if member_limit is None else member_limit)
                or total[0] > (MAX_EXPANDED_BYTES if total_limit is None else total_limit)):
            raise ValueError('Actual expanded size exceeds limit.')
        target.write(chunk)
    return count


def _stage(manager, archive, root):
    members = _index(archive)
    if 'library.json' not in members:
        raise ValueError('ZIP root must contain library.json.')
    total = [0]
    manifest = root / 'library.json'
    with archive.open(members['library.json']) as source, manifest.open('xb') as target:
        _stream(source, target, total)
    with manifest.open(encoding='utf-8') as source:
        data = json.load(source)
    assets = _catalog(manager, data, root)
    if set(members) != {'library.json', *assets}:
        raise ValueError('Archive must contain exactly the catalog and declared assets.')
    for relative, resolved in assets.items():
        target_path = Path(resolved)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(members[relative]) as source, target_path.open('xb') as target:
            _stream(source, target, total)
    return data


def export_library_zip(manager, name_or_path, archive_path):
    root = manager.get_folder_library_path(name_or_path)
    if root is None:
        raise ValueError('Only registered custom folder libraries can be exported.')
    output = Path(os.path.abspath(archive_path))
    if os.path.commonpath([root, os.path.realpath(output)]) == root:
        raise ValueError('Export output must be outside the source library.')
    if os.path.lexists(output):
        raise FileExistsError(f"Archive '{output}' already exists.")
    manager._validate_not_symlink_escape(root, os.path.join(root, 'library.json'))
    with open(os.path.join(root, 'library.json'), encoding='utf-8') as source:
        data = json.load(source)
    # This freshly decoded export copy must not share machine-local provenance.
    # Keep stored manifests untouched and validate every remaining value normally.
    if isinstance(data, dict) and isinstance(data.get('_metadata'), dict):
        data['_metadata'].pop('cloned_from', None)
    assets = _catalog(manager, data, Path(root))
    for relative, resolved in assets.items():
        # Even internal symlinks are refused for exchange, without changing duplication.
        current = Path(root)
        for part in relative.split('/'):
            current = current / part
            if current.is_symlink():
                raise ValueError('Symlink section assets cannot be exported.')
        if not os.path.isfile(resolved):
            raise FileNotFoundError(f"Missing declared asset '{relative}'.")
    fd, temporary = tempfile.mkstemp(prefix='.library-zip-', dir=output.parent)
    try:
        with os.fdopen(fd, 'w+b') as stream, zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('library.json', json.dumps(data, ensure_ascii=False, indent=2))
            total = [0]
            for relative, resolved in sorted(assets.items()):
                with open(resolved, 'rb') as source, archive.open(relative, 'w') as target:
                    _stream(source, target, total)
        with tempfile.TemporaryDirectory(prefix='mpf-zip-check-') as scratch:
            with zipfile.ZipFile(temporary) as archive:
                _stage(manager, archive, Path(scratch))
        # Prefer atomic no-clobber publication on filesystems supporting links.
        try:
            os.link(temporary, output)
        except OSError as error:
            if error.errno not in {errno.EPERM, errno.EOPNOTSUPP, errno.ENOTSUP, errno.ENOSYS}:
                raise
            # Exclusive creation also refuses racing files and symlinks. Unlike
            # linking, streaming exposes an incomplete file until close succeeds.
            with open(temporary, 'rb') as source:
                size = os.fstat(source.fileno()).st_size
                # On failure retain the partial output: path-based cleanup
                # could delete an unrelated replacement installed concurrently.
                with output.open('xb') as target:
                    copied = _stream(source, target, [0], size, size)
                    if copied != size:
                        raise ValueError('Archive size changed during publication.')
    finally:
        os.unlink(temporary)
    return str(output)


def import_library_zip(manager, archive_path, target_folder_path=None):
    manager._load_registry()
    with tempfile.TemporaryDirectory(prefix='mpf-zip-import-') as scratch:
        stage = Path(scratch)
        with zipfile.ZipFile(archive_path) as archive:
            data = _stage(manager, archive, stage)
        name = data['_metadata']['name']
        manager._check_name_collision(name)
        destination = Path(os.path.abspath(target_folder_path or manager.get_default_library_folder(name)))
        if os.path.lexists(destination):
            raise FileExistsError(f"Destination '{destination}' already exists.")
        # Only the newly claimed root is rollback-owned, never pre-existing parents.
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.mkdir()
        try:
            for child in stage.iterdir():
                target = destination / child.name
                if child.is_dir():
                    shutil.copytree(child, target)
                else:
                    shutil.copyfile(child, target)
            return manager.register_folder_library(str(destination))
        except Exception:
            shutil.rmtree(destination)
            raise
