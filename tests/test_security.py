from app.core.security import is_valid_tin, mask_tin, normalize_tin, sanitize_text


def test_valid_tin_3_digit_branch():
    assert is_valid_tin("307-265-187-000") is True


def test_valid_tin_5_digit_branch():
    # Real Favor Church data contains 5-digit branch codes.
    assert is_valid_tin("222-228-858-00000") is True


def test_invalid_tin_missing_branch_segment():
    assert is_valid_tin("248-551-556") is False


def test_tin_with_trailing_newline_normalizes_and_validates():
    # Real data contains TINs with a stray trailing "\n" from the spreadsheet.
    assert is_valid_tin("222-228-858-00000\n") is True


def test_normalize_tin_strips_whitespace():
    assert normalize_tin(" 222-228-858-00000\n") == "222-228-858-00000"


def test_mask_tin_hides_branch_segment():
    assert mask_tin("222-228-858-00000") == "222-228-858-XXXXX"


def test_mask_tin_handles_malformed_input_without_raising():
    assert mask_tin("248-551-556") == "248-551-556"


def test_sanitize_text_strips_control_characters():
    assert sanitize_text("Hello\x00World") == "HelloWorld"


def test_sanitize_text_none_stays_none():
    assert sanitize_text(None) is None


def test_sanitize_text_blank_becomes_none():
    assert sanitize_text("   ") is None
