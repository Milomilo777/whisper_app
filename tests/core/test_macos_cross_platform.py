"""Cross-platform (macOS) branch tests for the new session features.

This host is Windows; these tests FORCE the macOS / POSIX code paths so the
mac-correct branches are exercised even though no Mac is available.

We deliberately do NOT mutate the real ``os.name`` (that breaks ``pathlib``
on Windows — it refuses to instantiate ``PosixPath``). Instead each test
installs a tiny ``_PosixOs`` shim — a proxy that forwards every attribute to
the real ``os`` EXCEPT ``name`` (forced to ``"posix"``) — onto the specific
module under test (e.g. ``monitors.os``). That flips only the
``os.name == "nt"`` guards in that module while leaving stdlib intact.

They prove the guards added/verified during the macOS-support pass:

  * core.monitors: the ctypes Win32 probe NO-OPs off Windows (never touches
    ``ctypes.windll``), so detection degrades to screeninfo / single-monitor.
  * core.tiling: the ffplay binary name has NO ``.exe`` on mac, and
    ``extract_ffplay_from_zip`` writes the suffix-less ``ffplay``; the
    platform key for evermeet's download is ``"macos"``; the player spawns
    use ``new_session_kwargs`` (POSIX => ``start_new_session`` so a Stop
    killpg's the player's OWN group, not the whole app).
  * core.updates: the GitHub check is pure stdlib urllib — no winreg / Win32.

Hermetic: no tk.Tk(), no model, no real display, no network.
"""
from __future__ import annotations

import io
import os
import sys
import types
import zipfile

import pytest

from core import _proc, monitors, tiling


class _PosixOs:
    """Proxy to the real ``os`` module that reports ``name == "posix"``.

    Forwarding everything else (path, makedirs, listdir, getpgid, ...) keeps
    the module-under-test fully functional while flipping its
    ``os.name == "nt"`` guards to the macOS branch. pathlib (which reads the
    real ``os.name``) is untouched.
    """

    name = "posix"

    def __getattr__(self, item):
        return getattr(os, item)


def _force_posix(monkeypatch, module):
    monkeypatch.setattr(module, "os", _PosixOs())


# --------------------------------------------------------------------------- #
#  core.monitors — the Win32 ctypes path must NOT run on macOS
# --------------------------------------------------------------------------- #
def test_from_win32_noop_off_windows(monkeypatch):
    """``_from_win32`` returns [] off Windows via the early ``os.name`` guard,
    WITHOUT touching ``ctypes.windll`` (which does not exist on a real mac)."""
    _force_posix(monkeypatch, monitors)

    class _Boom:
        def __getattr__(self, _name):  # pragma: no cover - regression only
            raise AssertionError("ctypes.windll must not be used on macOS")

    monkeypatch.setattr(monitors.ctypes, "windll", _Boom(), raising=False)
    assert monitors._from_win32() == []


def test_list_monitors_mac_uses_screeninfo(monkeypatch):
    """On mac, screeninfo supplies monitors; the Win32 path is never reached."""
    _force_posix(monkeypatch, monitors)

    mod = types.ModuleType("screeninfo")

    class _M:
        def __init__(self, x, y, w, h, name, primary):
            self.x, self.y, self.width, self.height = x, y, w, h
            self.name, self.is_primary = name, primary

    mod.get_monitors = lambda: [  # type: ignore[attr-defined]
        _M(0, 0, 2560, 1440, "Built-in Retina Display", True),
    ]
    monkeypatch.setitem(sys.modules, "screeninfo", mod)
    # Guard: if screeninfo failed we must NOT silently fall into a Win32 probe.
    monkeypatch.setattr(
        monitors, "_from_win32",
        lambda: (_ for _ in ()).throw(AssertionError("Win32 path on mac")),
    )
    mons = monitors.list_monitors()
    assert len(mons) == 1
    assert mons[0]["width"] == 2560 and mons[0]["height"] == 1440
    assert mons[0]["name"] == "Built-in Retina Display"
    assert mons[0]["is_primary"] is True


def test_list_monitors_mac_single_fallback(monkeypatch):
    """No screeninfo + off-Windows => single-monitor fallback, no crash."""
    _force_posix(monkeypatch, monitors)
    monkeypatch.setitem(sys.modules, "screeninfo", None)  # import -> []
    mons = monitors.list_monitors()
    assert len(mons) == 1
    assert (mons[0]["width"], mons[0]["height"]) == (1920, 1080)
    assert mons[0]["index"] == 0


# --------------------------------------------------------------------------- #
#  core.tiling — ffplay name / extract / platform-key on macOS
# --------------------------------------------------------------------------- #
def test_ffplay_exe_name_has_no_exe_on_mac(monkeypatch):
    _force_posix(monkeypatch, tiling)
    assert tiling._ffplay_exe_name() == "ffplay"


def test_ffplay_platform_key_macos(monkeypatch):
    monkeypatch.setattr(tiling.sys, "platform", "darwin")
    assert tiling.ffplay_platform_key() == "macos"


def test_select_ffplay_url_macos(monkeypatch):
    monkeypatch.setattr(tiling.sys, "platform", "darwin")
    downloads = {
        "windows": "https://x/win.zip",
        "macos": "https://x/mac.zip",
    }
    # No explicit key -> resolves via the (forced-darwin) platform key.
    assert tiling.select_ffplay_url(downloads) == "https://x/mac.zip"


def _make_zip(tmp_path, members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in members.items():
            zf.writestr(name, content)
    p = tmp_path / "build.zip"
    p.write_bytes(buf.getvalue())
    return str(p)


def test_extract_ffplay_writes_suffixless_name_on_mac(monkeypatch, tmp_path):
    """On mac, extract flattens the member to ``ffplay`` (no .exe) + chmod +x.

    The evermeet/brew mac ffmpeg zip carries ``ffplay`` with no extension;
    forcing the posix branch must make the writer pick that target name.
    """
    _force_posix(monkeypatch, tiling)
    zip_path = _make_zip(tmp_path, {"ffmpeg-7.0/bin/ffplay": b"MAC-FFPLAY"})
    dest = tmp_path / "bin"
    out = tiling.extract_ffplay_from_zip(zip_path, str(dest))
    assert os.path.basename(out) == "ffplay"  # no .exe
    assert os.listdir(dest) == ["ffplay"]
    assert open(out, "rb").read() == b"MAC-FFPLAY"


def test_extract_ffplay_prefers_mac_name_over_exe(monkeypatch, tmp_path):
    """When a zip somehow has BOTH names, mac picks the suffix-less one."""
    _force_posix(monkeypatch, tiling)
    zip_path = _make_zip(tmp_path, {
        "bin/ffplay.exe": b"WIN",
        "bin/ffplay": b"MAC",
    })
    dest = tmp_path / "bin"
    out = tiling.extract_ffplay_from_zip(zip_path, str(dest))
    assert os.path.basename(out) == "ffplay"
    assert open(out, "rb").read() == b"MAC"


def test_download_ffplay_into_bin_on_mac(monkeypatch, tmp_path):
    """End-to-end (network stubbed): a mac .zip 'download' lands bin/ffplay."""
    _force_posix(monkeypatch, tiling)
    monkeypatch.setattr(tiling.sys, "platform", "darwin")
    # > 100 KB so the download size-guard accepts it as a real binary.
    src_zip = _make_zip(tmp_path, {"ffmpeg/bin/ffplay": b"OK" + b"\x00" * (110 * 1024)})
    bindir = tmp_path / "appbin"

    class _FakeResp:
        def __init__(self, data):
            self._b = io.BytesIO(data)

        def read(self, *a):
            return self._b.read(*a)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    data = open(src_zip, "rb").read()
    monkeypatch.setattr(
        tiling.urllib.request, "urlopen", lambda *a, **k: _FakeResp(data)
    )
    monkeypatch.setattr(tiling, "bin_dir", lambda: str(bindir))

    cfg = {"ffplay_downloads": {"macos": "https://x/ffmpeg-mac.zip"}}
    assert tiling.download_ffplay(config=cfg) is True
    assert os.path.isfile(bindir / "ffplay")
    assert not os.path.exists(bindir / "ffplay.exe")


# --------------------------------------------------------------------------- #
#  core.tiling — player spawns use new_session_kwargs (POSIX-safe teardown)
# --------------------------------------------------------------------------- #
def test_tiling_players_spawn_with_session_kwargs(monkeypatch):
    """The yt-dlp + ffplay Popens must carry ``new_session_kwargs()`` so that
    on POSIX they lead their OWN process group — otherwise a Stop's killpg
    would target the app's group and kill the whole app.

    We drive ``_start`` with stubbed binaries + a recording Popen and assert
    every spawn forwarded the session kwargs. Forcing ``_proc.os`` to the
    posix shim makes ``new_session_kwargs()`` return the POSIX shape.
    """
    _force_posix(monkeypatch, _proc)  # new_session_kwargs -> POSIX shape

    spawned: list[dict] = []

    class _FakePopen:
        def __init__(self, argv, **kwargs):
            spawned.append({"argv": list(argv), "kwargs": kwargs})
            self.pid = 1000 + len(spawned)
            self.stdout = io.BytesIO(b"")
            self.stderr = io.BytesIO(b"")
            self.stdin = io.BytesIO()

        def poll(self):
            return None

    monkeypatch.setattr(tiling.subprocess, "Popen", _FakePopen)
    # Pretend the tools resolve (avoid the RuntimeError guards in _start).
    monkeypatch.setattr(
        tiling, "bundled_binary", lambda name: "/usr/local/bin/" + name
    )
    monkeypatch.setattr(tiling.os.path, "isfile", lambda p: True)
    # Single monitor -> the single-window branch (one ffplay).
    monkeypatch.setattr(
        tiling._monitors, "list_monitors",
        lambda: [tiling._monitors.Monitor(
            index=0, x=0, y=0, width=1920, height=1080,
            name="Display 1", is_primary=True,
        )],
    )

    ctrl = tiling.TilingController()
    ctrl._url = "https://example.com/live"
    ctrl._divisions = 2
    ctrl._play_flag = True
    ctrl._start(ctrl._generation)  # run-token guard: pass the current generation

    assert len(spawned) >= 2  # yt-dlp + at least one ffplay
    for s in spawned:
        assert s["kwargs"].get("start_new_session") is True, s["argv"][:1]
        # On POSIX there must be NO Windows creationflags key.
        assert "creationflags" not in s["kwargs"], s["argv"][:1]
    # Defensive teardown (FakePopen has no real children; never raises).
    ctrl.stop()


def test_new_session_kwargs_posix_shape(monkeypatch):
    """Forced-POSIX: kwargs isolate the child (start_new_session) and carry
    NO Windows creationflags."""
    _force_posix(monkeypatch, _proc)
    kw = _proc.new_session_kwargs()
    assert kw == {"start_new_session": True}


# --------------------------------------------------------------------------- #
#  core.updates — pure stdlib, no Win32 / registry (cross-platform)
# --------------------------------------------------------------------------- #
def test_updates_check_is_silent_and_platform_neutral(monkeypatch):
    """``check_for_update`` uses urllib only; a stubbed 404 (private repo)
    returns None on any platform — no winreg / Win32 involved."""
    from core import updates

    def _boom(*a, **k):
        raise updates.urllib.error.HTTPError(
            "http://x", 404, "Not Found", {}, None  # type: ignore[arg-type]
        )

    monkeypatch.setattr(updates.urllib.request, "urlopen", _boom)
    # Pretend we're on mac for good measure; the code path is identical.
    monkeypatch.setattr(sys, "platform", "darwin")
    assert updates.check_for_update(timeout=1) is None


def test_updates_module_has_no_winreg_import():
    """Static guard: the update check must not import winreg / windll."""
    from core import updates as _u

    with open(_u.__file__, "r", encoding="utf-8") as fp:
        src = fp.read()
    assert "winreg" not in src
    assert "windll" not in src
