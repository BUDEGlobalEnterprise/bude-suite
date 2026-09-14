"""Catch missing imports in the Flutter apps without a Dart toolchain.

The development machine has no Flutter SDK, so nothing type-checks the mobile
code until it reaches the build machine. `context.l10n` is an extension on
BuildContext: using it without importing the file that declares the extension
compiles nowhere but reads fine in a diff. This bit three times during the
localization sweep, so it is a test now.
"""

import re
from pathlib import Path

import pytest

# app -> (extension member, file declaring it)
EXTENSIONS = {
    "flutter_app": ("context.l10n", "core/utils/locale_ext.dart"),
}


def _repo() -> Path:
    return next(
        parent
        for parent in Path(__file__).resolve().parents
        if (parent / "mobile-app").is_dir() and (parent / "backend").is_dir()
    )


@pytest.mark.parametrize("app,usage,declaring_file", [
    (app, usage, declaring) for app, (usage, declaring) in EXTENSIONS.items()
])
def test_extension_users_import_the_declaring_file(app, usage, declaring_file):
    lib = _repo() / "mobile-app" / app / "lib"
    assert (lib / declaring_file).is_file(), f"{declaring_file} moved or was renamed"

    basename = Path(declaring_file).name
    missing = [
        str(path.relative_to(lib))
        for path in sorted(lib.rglob("*.dart"))
        if usage in (text := path.read_text(encoding="utf-8"))
        and basename not in text
    ]

    assert missing == [], (
        f"{app}: these files use `{usage}` without importing {declaring_file}, "
        f"which will not compile: {missing}"
    )


@pytest.mark.parametrize("app", ["flutter_app", "hr_flutter_app",
                                 "helpdesk_flutter_app", "sales_flutter_app"])
def test_relative_imports_point_at_files_that_exist(app):
    """A renamed or moved file leaves danglers that only the compiler notices."""
    lib = _repo() / "mobile-app" / app / "lib"
    pattern = re.compile(r"^import '(\.[^']*)';", re.MULTILINE)

    dangling = []
    for path in sorted(lib.rglob("*.dart")):
        for target in pattern.findall(path.read_text(encoding="utf-8")):
            if not (path.parent / target).resolve().is_file():
                dangling.append(f"{path.relative_to(lib)} -> {target}")

    assert dangling == [], f"{app}: imports with no file behind them: {dangling}"
