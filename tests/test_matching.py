from core.matching.similarity import is_match, similarity_score
from core.matching.text_filter import is_plausible_dialogue_text


def test_exact_match():
    assert is_match("My mind rebels at stagnation", "My mind rebels at stagnation")


def test_ocr_noise_tolerant_match():
    # simulate common OCR slips: 'l' vs 'I', extra space, punctuation
    noisy = "My mind rebeIs at stagnation."
    assert similarity_score(noisy, "My mind rebels at stagnation") > 0.85


def test_unrelated_text_no_match():
    assert not is_match("Subscribe now for more", "My mind rebels at stagnation")


def test_filters_noise_tokens():
    assert not is_plausible_dialogue_text("--")
    assert not is_plausible_dialogue_text("12:34")
    assert is_plausible_dialogue_text("stagnation")
