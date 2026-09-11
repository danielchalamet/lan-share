"""Explicitly selected files; remote viewers see opaque IDs, never local paths."""
import pathlib
import secrets

EXTENSIONS = {'.mp4', '.m4v', '.mov', '.mkv', '.webm', '.mp3', '.m4a', '.aac', '.wav', '.ogg', '.flac'}


class MediaLibrary:
    def __init__(self, directory=None):
        self.files = {}
        if directory:
            root = pathlib.Path(directory).resolve()
            self.add([p for p in root.iterdir() if p.is_file() and p.suffix.lower() in EXTENSIONS and not p.is_symlink()])

    def add(self, paths):
        checked = []
        for value in paths:
            path = pathlib.Path(value).expanduser()
            if path.is_symlink() or not path.is_file() or path.suffix.lower() not in EXTENSIONS:
                raise ValueError('Выберите существующий медиафайл, а не ссылку на него.')
            checked.append(path.resolve())
        for path in checked:
            if path not in self.files.values():
                self.files[secrets.token_urlsafe(12)] = path

    def listing(self):
        return [{'id': key, 'name': path.name} for key, path in self.files.items()]

    def resolve(self, key):
        path = self.files.get(key)
        if path and path.is_file() and not path.is_symlink():
            return path
        return None

    def browse(self, value=None):
        home = pathlib.Path.home()
        default = home / 'Movies' if (home / 'Movies').is_dir() else home
        root = pathlib.Path(value).expanduser().resolve() if value else default
        if not root.is_dir():
            raise ValueError('Папка недоступна')
        entries = []
        try:
            for path in root.iterdir():
                if path.name.startswith('.') or path.is_symlink():
                    continue
                if path.is_dir() or (path.is_file() and path.suffix.lower() in EXTENSIONS):
                    entries.append({'name': path.name, 'path': str(path), 'directory': path.is_dir()})
        except PermissionError as error:
            raise ValueError('Нет доступа к этой папке. Выберите другую или проверьте разрешения Terminal.') from error
        return {'path': str(root), 'parent': str(root.parent),
                'entries': sorted(entries, key=lambda e: (not e['directory'], e['name'].lower()))}
