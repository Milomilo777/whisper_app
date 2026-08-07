"""Tests for the adaptive audio-denoise pre-process (core/denoise.py).

The numbers in the verification tests are not invented: they are the
measured before/after values from calibrating the feature against real
ffmpeg output on SAPI-generated speech at several noise levels. Keeping
them here means a future tweak to the thresholds has to consciously
re-justify itself against real material.
"""
from __future__ import annotations

import math

import pytest

from core import denoise as dn


# Verbatim ffmpeg stderr (ffmpeg 2026-05-06, bundled build). Real output
# is the only trustworthy fixture for a log-scraping parser — ffmpeg's
# format is not a stable API and its "RMS through dB" is an upstream
# typo for "trough" that a hand-written fixture would silently correct.
REAL_STDERR = """\
[Parsed_astats_1 @ 000000000016a100] Overall
[Parsed_astats_1 @ 000000000016a100] DC offset: -0.000032
[Parsed_astats_1 @ 000000000016a100] Min level: -2419.000000
[Parsed_astats_1 @ 000000000016a100] Max difference: 1663.000000
[Parsed_astats_1 @ 000000000016a100] Peak level dB: -22.419700
[Parsed_astats_1 @ 000000000016a100] RMS level dB: -28.804796
[Parsed_astats_1 @ 000000000016a100] RMS peak dB: -26.943199
[Parsed_astats_1 @ 000000000016a100] RMS through dB: -50.810578
[Parsed_astats_1 @ 000000000016a100] Flat factor: 0.000000
[Parsed_astats_1 @ 000000000016a100] Noise floor dB: -46.558319
[Parsed_astats_1 @ 000000000016a100] Noise floor count: 4.000000
[Parsed_astats_1 @ 000000000016a100] Entropy: 0.668599
[Parsed_astats_1 @ 000000000016a100] Bit depth: 12/16/16/16
[Parsed_astats_1 @ 000000000016a100] Number of samples: 192000
[Parsed_astats_4 @ 000000000016b200] Overall
[Parsed_astats_4 @ 000000000016b200] Peak level dB: -24.100000
[Parsed_astats_4 @ 000000000016b200] RMS level dB: -30.120000
[Parsed_astats_4 @ 000000000016b200] RMS peak dB: -28.400000
[Parsed_astats_4 @ 000000000016b200] Noise floor dB: -48.000000
[Parsed_astats_4 @ 000000000016b200] Entropy: 0.640000
"""

PRISTINE_STDERR = """\
[Parsed_astats_1 @ 00000000006b8000] Overall
[Parsed_astats_1 @ 00000000006b8000] Peak level dB: -23.330959
[Parsed_astats_1 @ 00000000006b8000] RMS level dB: -28.848775
[Parsed_astats_1 @ 00000000006b8000] RMS peak dB: -27.070187
[Parsed_astats_1 @ 00000000006b8000] Noise floor dB: -inf
[Parsed_astats_1 @ 00000000006b8000] Entropy: 0.343821
"""


# ------------------------------------------------------------------ parsing


def test_parse_real_stderr_returns_both_blocks():
    blocks = dn.parse_astats_blocks(REAL_STDERR)
    assert len(blocks) == 2
    assert blocks[0]["rms_level"] == pytest.approx(-28.804796)
    assert blocks[0]["noise_floor"] == pytest.approx(-46.558319)
    assert blocks[1]["rms_level"] == pytest.approx(-30.120000)


def test_parse_maps_ffmpeg_trough_typo():
    """ffmpeg prints 'RMS through dB'; AudioStats must still populate."""
    blocks = dn.parse_astats_blocks(REAL_STDERR)
    stats = dn.AudioStats.from_metrics(blocks[0])
    assert stats.rms_trough == pytest.approx(-50.810578)


def test_parse_handles_negative_infinity():
    blocks = dn.parse_astats_blocks(PRISTINE_STDERR)
    assert blocks[0]["noise_floor"] == float("-inf")


def test_parse_skips_non_numeric_and_unrelated_lines():
    blocks = dn.parse_astats_blocks(REAL_STDERR)
    # "Bit depth: 12/16/16/16" is not a float and must not appear.
    assert "bit_depth" not in blocks[0]


def test_parse_ignores_lines_before_any_overall_header():
    stderr = "[Parsed_astats_1 @ 0x1] RMS level dB: -10.0\n"
    assert dn.parse_astats_blocks(stderr) == []


def test_parse_empty_input():
    assert dn.parse_astats_blocks("") == []


# ------------------------------------------- full-band vs speech-band split


def test_split_uses_energy_invariant_not_print_order():
    """Band-passing can only remove energy, so the quieter block is the band.

    Guards against a future ffmpeg reordering its filter teardown and
    silently swapping the two measurements.
    """
    blocks = dn.parse_astats_blocks(REAL_STDERR)
    full, band = dn.split_full_and_band(blocks)
    assert full is not None and band is not None
    assert full.rms_level == pytest.approx(-28.804796)
    assert band.rms_level == pytest.approx(-30.120000)

    reversed_full, reversed_band = dn.split_full_and_band(list(reversed(blocks)))
    assert reversed_full is not None and reversed_band is not None
    assert reversed_full.rms_level == pytest.approx(-28.804796)
    assert reversed_band.rms_level == pytest.approx(-30.120000)


def test_split_single_block_has_no_band():
    blocks = dn.parse_astats_blocks(PRISTINE_STDERR)
    full, band = dn.split_full_and_band(blocks)
    assert full is not None
    assert band is None


def test_split_no_blocks():
    assert dn.split_full_and_band([]) == (None, None)


# --------------------------------------------------------------- SNR estimate


def test_estimate_snr_from_real_measurement():
    blocks = dn.parse_astats_blocks(REAL_STDERR)
    stats = dn.AudioStats.from_metrics(blocks[0])
    # rms_level -28.80 dominates rms_peak-10 (-36.94); floor -46.56.
    assert dn.estimate_snr_db(stats) == pytest.approx(17.75, abs=0.05)


def test_estimate_snr_is_infinite_without_a_noise_floor():
    stats = dn.AudioStats(rms_level=-28.8, rms_peak=-27.0,
                          noise_floor=float("-inf"))
    assert dn.estimate_snr_db(stats) == float("inf")


def test_estimate_snr_uses_rms_peak_when_speech_is_sparse():
    """A mostly-silent file understates speech level via overall RMS.

    Without the rms_peak fallback the SNR would read 10 dB lower and
    over-trigger denoising on a quiet-but-clean recording.
    """
    sparse = dn.AudioStats(rms_level=-50.0, rms_peak=-20.0, noise_floor=-60.0)
    assert dn.estimate_snr_db(sparse) == pytest.approx(30.0)


def test_estimate_snr_nan_when_unmeasurable():
    assert math.isnan(dn.estimate_snr_db(dn.AudioStats()))


# ------------------------------------------------------------ level decision


@pytest.mark.parametrize(
    "snr, expected",
    [
        (float("inf"), "off"),
        (60.0, "off"),
        (30.0, "off"),
        (29.9, "light"),
        (20.0, "light"),
        (19.9, "medium"),
        (10.0, "medium"),
        (9.9, "strong"),
        (0.0, "strong"),
        (-10.0, "strong"),
    ],
)
def test_decide_level_auto_thresholds(snr, expected):
    assert dn.decide_level(snr, "auto") == expected


def test_decide_level_never_denoises_on_an_unusable_measurement():
    assert dn.decide_level(float("nan"), "auto") == "off"


@pytest.mark.parametrize("forced", ["off", "light", "medium", "strong"])
def test_decide_level_explicit_overrides_measurement(forced):
    """A named level is honoured even on audio that measures pristine."""
    assert dn.decide_level(float("inf"), forced) == forced
    assert dn.decide_level(2.0, forced) == forced


def test_decide_level_unknown_string_falls_back_to_auto():
    assert dn.decide_level(5.0, "aggressive") == "strong"
    assert dn.decide_level(50.0, "aggressive") == "off"


# -------------------------------------------------------------- filter chain


@pytest.mark.parametrize("level", ["light", "medium", "strong"])
def test_chain_is_parameterised_by_the_measured_noise_floor(level):
    chain = dn.build_filter_chain(level, -46.6)
    assert "nf=-46.6" in chain
    assert "afftdn" in chain
    assert "highpass" in chain
    assert "tn=1" in chain


def test_chain_off_and_unknown_are_empty():
    assert dn.build_filter_chain("off", -50.0) == ""
    assert dn.build_filter_chain("nonsense", -50.0) == ""


@pytest.mark.parametrize("level", ["light", "medium", "strong"])
def test_chain_never_contains_anlmdn(level):
    """Regression guard: anlmdn segfaults in the bundled ffmpeg build.

    Identical arguments crashed one run and succeeded the next; with it
    removed the strong chain survived 20/20 repeats. Do not reintroduce
    it without re-running that stability check.
    """
    assert "anlmdn" not in dn.build_filter_chain(level, -50.0)


@pytest.mark.parametrize("level", ["light", "medium", "strong"])
def test_chain_reduction_depth_stays_below_musical_noise(level):
    """nr above ~24 dB produces artefacts that hurt ASR more than noise."""
    chain = dn.build_filter_chain(level, -50.0)
    nr = float(chain.split("nr=")[1].split(":")[0])
    assert 0 < nr <= 24


def test_chain_strength_increases_with_level():
    def nr_of(level):
        return float(dn.build_filter_chain(level, -50.0).split("nr=")[1].split(":")[0])

    assert nr_of("light") < nr_of("medium") < nr_of("strong")


@pytest.mark.parametrize(
    "measured, expected",
    [
        (-46.6, -46.6),
        (-120.0, dn.NF_MIN_DB),       # below afftdn's accepted range
        (-5.0, dn.NF_MAX_DB),         # above it
        (float("-inf"), dn.NF_FALLBACK_DB),
        (float("inf"), dn.NF_FALLBACK_DB),
        (float("nan"), dn.NF_FALLBACK_DB),
    ],
)
def test_noise_floor_is_clamped_into_afftdn_range(measured, expected):
    assert dn.clamp_noise_floor(measured) == pytest.approx(expected)


def test_analysis_graph_measures_the_speech_band():
    graph = dn.analysis_filter_complex()
    assert f"highpass=f={dn.SPEECH_BAND_LOW_HZ}" in graph
    assert f"lowpass=f={dn.SPEECH_BAND_HIGH_HZ}" in graph
    assert graph.count("astats") == 2


# ------------------------------------------------------------ sampling windows


def test_short_files_are_scanned_whole():
    assert dn.sample_windows(60.0) == [(0.0, 0.0)]
    assert dn.sample_windows(dn.FULL_SCAN_MAX_S) == [(0.0, 0.0)]


def test_unknown_duration_scans_whole():
    assert dn.sample_windows(0.0) == [(0.0, 0.0)]
    assert dn.sample_windows(float("nan")) == [(0.0, 0.0)]


def test_long_files_are_sampled_at_bounded_cost():
    """Analysis cost must not grow with duration."""
    for duration in (600.0, 3600.0, 10800.0):
        windows = dn.sample_windows(duration)
        assert len(windows) == len(dn.SAMPLE_POSITIONS)
        assert all(length == dn.SAMPLE_WINDOW_S for _, length in windows)
        total = sum(length for _, length in windows)
        assert total == dn.SAMPLE_WINDOW_S * len(dn.SAMPLE_POSITIONS)


def test_sample_windows_stay_inside_the_file():
    duration = 600.0
    for start, length in dn.sample_windows(duration):
        assert start >= 0.0
        assert start + length <= duration


def test_sample_windows_are_ordered_and_spread():
    starts = [s for s, _ in dn.sample_windows(3600.0)]
    assert starts == sorted(starts)
    assert len(set(starts)) == len(starts)


# ------------------------------------------------------- verification guards


def test_allowed_band_drop_scales_with_measured_noise():
    """A noisy file legitimately loses more energy than a clean one.

    Without this scaling the guard rejects exactly the heavy-noise cases
    the feature exists for.
    """
    clean = dn.allowed_band_drop_db(30.0)
    moderate = dn.allowed_band_drop_db(12.0)
    noisy = dn.allowed_band_drop_db(1.0)
    assert clean < moderate < noisy


def test_allowed_band_drop_matches_the_physical_model():
    # At 0 dB SNR noise carries half the power -> 3.01 dB expected loss.
    assert dn.allowed_band_drop_db(0.0) == pytest.approx(
        3.0103 + dn.BAND_TOLERANCE_DB, abs=0.01
    )


def test_allowed_band_drop_on_pristine_audio_is_just_the_tolerance():
    assert dn.allowed_band_drop_db(float("inf")) == dn.BAND_TOLERANCE_DB
    assert dn.allowed_band_drop_db(float("nan")) == dn.BAND_TOLERANCE_DB


def _profile(snr, band_rms, entropy):
    return dn.NoiseProfile(
        full=dn.AudioStats(rms_level=-28.0, rms_peak=-26.0,
                           noise_floor=-46.0, entropy=entropy),
        speech_band=dn.AudioStats(rms_level=band_rms, entropy=entropy),
        snr_db=snr,
    )


@pytest.mark.parametrize(
    "label, snr, band_drop, entropy_drop",
    [
        # Measured on real speech: level, baseline SNR, speech-band drop,
        # entropy drop. All of these are legitimate work and must survive.
        ("light @ 20.8 dB", 20.8, 0.278, 0.003),
        ("medium @ 12.4 dB", 12.4, 0.416, 0.015),
        ("strong @ 6.9 dB", 6.9, 0.708, 0.025),
        ("strong @ 1.2 dB", 1.2, 2.022, 0.059),
        ("strong @ -2.2 dB", -2.2, 3.016, 0.050),
    ],
)
def test_verdict_keeps_measured_legitimate_results(label, snr, band_drop,
                                                   entropy_drop):
    before = _profile(snr, -22.0, 0.700)
    after = _profile(snr + 8.0, -22.0 - band_drop, 0.700 - entropy_drop)
    keep, reason = dn.verdict(before, after)
    assert keep, f"{label} was wrongly reverted: {reason}"


def test_verdict_reverts_spectral_over_suppression():
    """afftdn nr=60: measured 1.214 dB speech-band loss at ~30 dB SNR."""
    before = _profile(30.6, -22.0, 0.700)
    after = _profile(float("inf"), -22.0 - 1.214, 0.700 - 0.092)
    keep, reason = dn.verdict(before, after)
    assert not keep
    assert "speech-band" in reason


def test_verdict_reverts_gating_that_the_energy_guard_misses():
    """A hard gate barely moves band energy but collapses entropy.

    This is the case that proves one guard is not enough: measured
    band drop 0.183 dB (passes) with entropy drop 0.151 (fails).
    """
    before = _profile(30.6, -22.0, 0.700)
    after = _profile(float("inf"), -22.0 - 0.183, 0.700 - 0.151)
    keep, reason = dn.verdict(before, after)
    assert not keep
    assert "entropy" in reason


def test_verdict_reverts_when_verification_is_unavailable():
    before = _profile(20.0, -22.0, 0.7)
    after = dn.NoiseProfile(full=dn.AudioStats(), speech_band=None, snr_db=25.0)
    keep, reason = dn.verdict(before, after)
    assert not keep
    assert "unavailable" in reason


def test_verdict_reverts_when_band_rms_is_unreadable():
    before = _profile(20.0, -22.0, 0.7)
    after = _profile(25.0, float("nan"), 0.7)
    keep, _ = dn.verdict(before, after)
    assert not keep


# --------------------------------------------------------- behaviour matrix


@pytest.fixture
def src(tmp_path):
    p = tmp_path / "audio.wav"
    p.write_bytes(b"\x00" * 8192)
    return str(p)


def test_disabled_returns_input_without_touching_ffmpeg(src, monkeypatch):
    monkeypatch.setattr(
        dn, "analyze",
        lambda *a, **kw: pytest.fail("analysis ran while denoise was disabled"),
    )
    assert dn.denoise_audio(src, enabled=False) == src


def test_missing_ffmpeg_returns_input(src, monkeypatch):
    monkeypatch.setattr(dn, "is_available", lambda: False)
    logs: list[str] = []
    assert dn.denoise_audio(src, log=logs.append) == src
    assert any("ffmpeg" in line.lower() for line in logs)


def test_unmeasurable_audio_is_left_alone(src, monkeypatch):
    monkeypatch.setattr(dn, "is_available", lambda: True)
    monkeypatch.setattr(dn, "analyze", lambda *a, **kw: None)
    assert dn.denoise_audio(src) == src


def test_clean_audio_is_left_completely_untouched(src, monkeypatch, tmp_path):
    """The headline behaviour: measuring clean means doing nothing."""
    monkeypatch.setattr(dn, "is_available", lambda: True)
    monkeypatch.setattr(dn, "cache_dir", lambda: tmp_path / "cache")
    monkeypatch.setattr(
        dn, "analyze",
        lambda *a, **kw: dn.NoiseProfile(
            full=dn.AudioStats(rms_level=-20.0, rms_peak=-18.0,
                               noise_floor=float("-inf"), entropy=0.34),
            speech_band=dn.AudioStats(rms_level=-22.0, entropy=0.34),
            snr_db=float("inf"),
        ),
    )
    monkeypatch.setattr(
        dn, "_apply_chain",
        lambda *a, **kw: pytest.fail("filtered audio that measured clean"),
    )
    logs: list[str] = []
    assert dn.denoise_audio(src, log=logs.append) == src
    assert any("already clean" in line for line in logs)


def test_ffmpeg_failure_falls_back_to_the_original(src, monkeypatch, tmp_path):
    monkeypatch.setattr(dn, "is_available", lambda: True)
    monkeypatch.setattr(dn, "cache_dir", lambda: tmp_path / "cache")
    monkeypatch.setattr(dn, "analyze", lambda *a, **kw: _profile(12.0, -22.0, 0.7))
    monkeypatch.setattr(dn, "_apply_chain", lambda *a, **kw: False)
    logs: list[str] = []
    assert dn.denoise_audio(src, log=logs.append) == src
    assert any("original" in line for line in logs)


def test_failed_verification_reverts_and_removes_the_render(src, monkeypatch,
                                                            tmp_path):
    cache = tmp_path / "cache"
    monkeypatch.setattr(dn, "is_available", lambda: True)
    monkeypatch.setattr(dn, "cache_dir", lambda: cache)

    calls: list[str] = []

    def fake_analyze(path, **kw):
        calls.append(path)
        if len(calls) == 1:
            return _profile(30.0, -22.0, 0.700)
        return _profile(float("inf"), -22.0 - 5.0, 0.700 - 0.3)

    def fake_apply(_src, dst, _chain, **kw):
        cache.mkdir(parents=True, exist_ok=True)
        with open(dst, "wb") as fp:
            fp.write(b"\x00" * 4096)
        return True

    monkeypatch.setattr(dn, "analyze", fake_analyze)
    monkeypatch.setattr(dn, "_apply_chain", fake_apply)
    logs: list[str] = []
    assert dn.denoise_audio(src, level="medium", log=logs.append) == src
    assert any("reverted" in line for line in logs)
    # The rejected render must not survive as a stray file.
    assert list(cache.glob("*.wav")) == []
    assert list(cache.glob("*.part")) == []


def test_successful_run_returns_the_render(src, monkeypatch, tmp_path):
    cache = tmp_path / "cache"
    monkeypatch.setattr(dn, "is_available", lambda: True)
    monkeypatch.setattr(dn, "cache_dir", lambda: cache)

    calls: list[str] = []

    def fake_analyze(path, **kw):
        calls.append(path)
        if len(calls) == 1:
            return _profile(12.0, -22.0, 0.700)
        return _profile(22.0, -22.4, 0.690)

    def fake_apply(_src, dst, _chain, **kw):
        cache.mkdir(parents=True, exist_ok=True)
        with open(dst, "wb") as fp:
            fp.write(b"\x00" * 4096)
        return True

    monkeypatch.setattr(dn, "analyze", fake_analyze)
    monkeypatch.setattr(dn, "_apply_chain", fake_apply)
    logs: list[str] = []
    out = dn.denoise_audio(src, log=logs.append)
    assert out != src
    assert out.endswith("_denoised.wav")
    assert any("Denoise applied" in line for line in logs)
    # No staging file left behind.
    assert list(cache.glob("*.part")) == []


def test_explicit_level_hits_the_cache_without_analysing(src, monkeypatch,
                                                         tmp_path):
    cache = tmp_path / "cache"
    monkeypatch.setattr(dn, "is_available", lambda: True)
    monkeypatch.setattr(dn, "cache_dir", lambda: cache)
    cached = dn._cached_path(src, "medium")
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(b"\x00" * 4096)
    monkeypatch.setattr(
        dn, "analyze", lambda *a, **kw: pytest.fail("analysed on a cache hit")
    )
    assert dn.denoise_audio(src, level="medium") == str(cached)


def test_explicit_off_level_short_circuits(src, monkeypatch):
    monkeypatch.setattr(dn, "is_available", lambda: True)
    monkeypatch.setattr(
        dn, "analyze", lambda *a, **kw: pytest.fail("analysed with level=off")
    )
    assert dn.denoise_audio(src, level="off") == src


def test_transient_mode_writes_beside_the_work_dir(src, monkeypatch, tmp_path):
    """A pre-sliced clip must not pollute the shared cache.

    Its key includes a temp path that can never be hit again.
    """
    work = tmp_path / "partials"
    monkeypatch.setattr(dn, "is_available", lambda: True)
    monkeypatch.setattr(
        dn, "cache_dir", lambda: pytest.fail("used the cache for transient input")
    )

    calls: list[str] = []

    def fake_analyze(path, **kw):
        calls.append(path)
        return (_profile(12.0, -22.0, 0.700) if len(calls) == 1
                else _profile(22.0, -22.4, 0.690))

    def fake_apply(_src, dst, _chain, **kw):
        with open(dst, "wb") as fp:
            fp.write(b"\x00" * 4096)
        return True

    monkeypatch.setattr(dn, "analyze", fake_analyze)
    monkeypatch.setattr(dn, "_apply_chain", fake_apply)
    out = dn.denoise_audio(src, cache=False, work_dir=work)
    assert out.endswith(".denoised.wav")
    assert work in __import__("pathlib").Path(out).parents


def test_never_raises_even_on_an_unexpected_internal_error(src, monkeypatch):
    """A denoise bug must never cost the user their transcription."""
    def boom(*a, **kw):
        raise ValueError("kaboom")

    monkeypatch.setattr(dn, "_denoise_audio_inner", boom)
    logs: list[str] = []
    assert dn.denoise_audio(src, log=logs.append) == src
    assert any("kaboom" in line for line in logs)


# ------------------------------------------------------------------- cache


def test_prune_cache_evicts_oldest_beyond_budget(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr(dn, "cache_dir", lambda: cache)
    for i in range(4):
        p = cache / f"{i:016x}_denoised.wav"
        p.write_bytes(b"\x00" * (1024 * 1024))
        import os as _os
        _os.utime(p, (1_000_000 + i, 1_000_000 + i))
    removed = dn.prune_cache(budget_mb=2)
    assert removed == 2
    assert len(list(cache.glob("*_denoised.wav"))) == 2


def test_prune_cache_never_evicts_the_keeper(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr(dn, "cache_dir", lambda: cache)
    import os as _os
    keeper = cache / "aaaa_denoised.wav"
    keeper.write_bytes(b"\x00" * (2 * 1024 * 1024))
    _os.utime(keeper, (1_000_000, 1_000_000))  # oldest -> first to go
    other = cache / "bbbb_denoised.wav"
    other.write_bytes(b"\x00" * (2 * 1024 * 1024))
    _os.utime(other, (2_000_000, 2_000_000))
    dn.prune_cache(budget_mb=1, keep=str(keeper))
    assert keeper.exists()


def test_prune_cache_budget_zero_disables_eviction(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr(dn, "cache_dir", lambda: cache)
    (cache / "x_denoised.wav").write_bytes(b"\x00" * 4096)
    assert dn.prune_cache(budget_mb=0) == 0
    assert len(list(cache.glob("*_denoised.wav"))) == 1


def test_prune_cache_on_missing_dir_is_a_no_op(tmp_path, monkeypatch):
    monkeypatch.setattr(dn, "cache_dir", lambda: tmp_path / "nope")
    assert dn.prune_cache(budget_mb=1) == 0


def test_cache_key_changes_with_level(src):
    assert dn._cache_key(src, "light") != dn._cache_key(src, "strong")


def test_cache_key_changes_when_the_source_changes(src, tmp_path):
    first = dn._cache_key(src, "medium")
    import os as _os
    with open(src, "wb") as fp:
        fp.write(b"\x01" * 16384)
    _os.utime(src, (2_000_000, 2_000_000))
    assert dn._cache_key(src, "medium") != first


def test_clear_cache_is_safe_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(dn, "cache_dir", lambda: tmp_path / "gone")
    dn.clear_cache()  # must not raise


# ------------------------------------------------------------ config surface


def test_config_defaults_are_conservative():
    from core.config import DEFAULT_CONFIG

    assert DEFAULT_CONFIG["denoise_enabled"] is False
    assert DEFAULT_CONFIG["denoise_level"] == "auto"
    assert DEFAULT_CONFIG["denoise_level"] in dn.LEVEL_CHOICES


# ------------------------------------------------- real ffmpeg (skipped w/o it)
#
# Everything above mocks ffmpeg, so a malformed filter string or a
# parameter this ffmpeg build rejects would pass every one of those
# tests. These few run the real binary end to end. They generate their
# own audio via lavfi, so they need no fixture file — only ffmpeg.

requires_ffmpeg = pytest.mark.skipif(
    not dn.is_available(), reason="ffmpeg not available"
)


def _synth(path, *, noise: str, seconds: float = 6.0) -> None:
    """Render a tone-burst 'speech' signal plus optional pink noise."""
    import subprocess

    from core.paths import bundled_binary

    speech = (f"sine=frequency=300:duration={seconds},"
              f"volume='if(lt(mod(t,3),2),0.5,0.0)':eval=frame")
    if noise:
        cmd = [
            bundled_binary("ffmpeg"), "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", speech,
            "-f", "lavfi", "-i",
            f"anoisesrc=color=pink:duration={seconds}:amplitude={noise}",
            "-filter_complex", "[0][1]amix=inputs=2:duration=shortest:normalize=0",
            "-ac", "1", "-ar", "16000", "-y", str(path),
        ]
    else:
        cmd = [
            bundled_binary("ffmpeg"), "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", speech,
            "-ac", "1", "-ar", "16000", "-y", str(path),
        ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)


@requires_ffmpeg
@pytest.mark.parametrize("level", ["light", "medium", "strong"])
def test_real_ffmpeg_accepts_every_shipped_chain(level, tmp_path):
    """Each chain must actually parse and run in the bundled ffmpeg."""
    src = tmp_path / "in.wav"
    dst = tmp_path / "out.wav"
    _synth(src, noise="0.02")
    chain = dn.build_filter_chain(level, -46.6)
    assert dn._apply_chain(str(src), str(dst), chain, duration_s=6.0) is True
    assert dst.stat().st_size > dn._MIN_OUTPUT_BYTES


@requires_ffmpeg
def test_real_analysis_separates_noisy_from_clean(tmp_path):
    clean = tmp_path / "clean.wav"
    noisy = tmp_path / "noisy.wav"
    _synth(clean, noise="")
    _synth(noisy, noise="0.05")

    clean_profile = dn.analyze(str(clean), duration_s=6.0)
    noisy_profile = dn.analyze(str(noisy), duration_s=6.0)
    assert clean_profile is not None and noisy_profile is not None
    # Both blocks must have been measured, or verification cannot run.
    assert noisy_profile.speech_band is not None
    assert noisy_profile.snr_db < clean_profile.snr_db
    assert dn.decide_level(clean_profile.snr_db, "auto") == "off"
    assert dn.decide_level(noisy_profile.snr_db, "auto") != "off"


@requires_ffmpeg
def test_real_end_to_end_denoises_noisy_and_skips_clean(tmp_path, monkeypatch):
    monkeypatch.setattr(dn, "cache_dir", lambda: tmp_path / "cache")

    clean = tmp_path / "clean.wav"
    _synth(clean, noise="")
    assert dn.denoise_audio(str(clean), duration_s=6.0) == str(clean)

    noisy = tmp_path / "noisy.wav"
    _synth(noisy, noise="0.05")
    logs: list[str] = []
    out = dn.denoise_audio(str(noisy), duration_s=6.0, log=logs.append)
    assert out != str(noisy), f"expected a render; logs={logs}"
    assert out.endswith("_denoised.wav")
    # The render must survive its own verification, and improve the metric.
    before = dn.analyze(str(noisy), duration_s=6.0)
    after = dn.analyze(out, duration_s=6.0)
    assert before is not None and after is not None
    assert after.snr_db > before.snr_db


@requires_ffmpeg
def test_real_ffmpeg_rejects_a_missing_input_without_raising(tmp_path):
    missing = tmp_path / "nope.wav"
    assert dn.analyze(str(missing), duration_s=6.0) is None
    assert dn.denoise_audio(str(missing), duration_s=6.0) == str(missing)


def test_denoise_settings_invalidate_a_resume_checkpoint():
    """Resuming with different pre-processing would splice mismatched halves."""
    from core._checkpoint import _CONFIG_FINGERPRINT_KEYS, config_fingerprint

    assert "denoise_enabled" in _CONFIG_FINGERPRINT_KEYS
    assert "denoise_level" in _CONFIG_FINGERPRINT_KEYS
    a = config_fingerprint({"denoise_enabled": False, "denoise_level": "auto"})
    b = config_fingerprint({"denoise_enabled": True, "denoise_level": "auto"})
    c = config_fingerprint({"denoise_enabled": True, "denoise_level": "strong"})
    assert a != b != c and a != c
