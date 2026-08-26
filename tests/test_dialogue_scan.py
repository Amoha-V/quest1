from core.dialogue_scan import DialogueOccurrence, _find_existing, scan_first_dialogue


def _occ(text, ts=0.0):
    return DialogueOccurrence(
        text=text, first_timestamp_sec=ts, frame_number=0, confidence=0.9, bbox=(0, 0, 1, 1)
    )


def test_new_line_not_matched_to_unrelated_known_lines():
    known = [_occ("My mind rebels at stagnation")]
    assert _find_existing("Subscribe now for more", known) is None


def test_noisy_rereading_of_same_line_matches_existing():
    known = [_occ("My mind rebels at stagnation")]
    # OCR misread of the same on-screen line a few frames later
    match = _find_existing("My mind rebeIs at stagnation.", known)
    assert match is known[0]


def test_first_seen_wins_when_multiple_known_lines_are_similar():
    known = [_occ("hello there", ts=1.0), _occ("hello there general", ts=5.0)]
    match = _find_existing("hello there", known)
    # should fold into whichever known line is the closer/best match, not
    # silently create a third near-duplicate entry
    assert match in known


def test_scan_first_dialogue_stops_at_earliest_detection(monkeypatch):
    """scan_first_dialogue must not keep walking after the first hit."""
    from core.source.metadata import VideoMetadata
    from pathlib import Path
    import core.dialogue_scan as ds

    meta = VideoMetadata(
        duration_sec=10.0,
        fps=25.0,
        width=320,
        height=180,
    )
    calls = {"n": 0}

    def fake_scans(_video_path, _meta, on_progress=None):
        # would continue past 2.0 if the scanner failed to stop
        for ts in (0.0, 1.0, 2.0, 3.0, 4.0):
            calls["n"] += 1
            yield ts, []

    def fake_best(_detections):
        # first two frames empty; third (ts=2.0) has dialogue
        if calls["n"] < 3:
            return None
        return ("My mind rebels at stagnation", 0.95, (10, 20, 100, 30))

    monkeypatch.setattr(ds, "iter_scan_detections", fake_scans)
    monkeypatch.setattr(ds, "_best_detection", fake_best)

    result = scan_first_dialogue(Path("dummy.mp4"), meta)
    assert result is not None
    assert result.text == "My mind rebels at stagnation"
    assert result.first_timestamp_sec == 2.0
    # stopped after the hit at 2.0 -- never sampled 3.0 / 4.0
    assert calls["n"] == 3
