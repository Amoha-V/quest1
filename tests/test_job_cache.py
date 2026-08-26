from service.workers.video_worker import job_id_for, normalize_dialogue


def test_normalize_dialogue_collapses_case_and_space():
    assert normalize_dialogue("  My  Mind Rebels  ") == "my mind rebels"
    assert normalize_dialogue(None) == ""
    assert normalize_dialogue("") == ""


def test_job_id_same_video_and_dialogue_is_stable():
    url = "https://ok.ru/video/248244667877"
    a = job_id_for(url, "My mind rebels at stagnation", scan_all=False)
    b = job_id_for(url, "  my mind rebels at stagnation  ", scan_all=False)
    assert a == b
    assert a.endswith(":first")


def test_job_id_differs_for_scan_all_and_different_text():
    url = "https://ok.ru/video/248244667877"
    first = job_id_for(url, "My mind rebels at stagnation", scan_all=False)
    all_mode = job_id_for(url, "My mind rebels at stagnation", scan_all=True)
    other = job_id_for(url, "Something else", scan_all=False)
    assert first != all_mode
    assert first != other
    assert all_mode.endswith(":all")
