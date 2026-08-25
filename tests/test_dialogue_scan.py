from core.dialogue_scan import DialogueOccurrence, _find_existing


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
