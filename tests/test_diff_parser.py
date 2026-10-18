from app.services.diff_parser import is_binary_or_skipped, parse_patch, parse_pr_files


def test_parse_simple_addition():
    patch = "@@ -0,0 +1,3 @@\n+line1\n+line2\n+line3"
    result = parse_patch(patch)
    assert result == {1: 2, 2: 3, 3: 4}


def test_parse_mixed_changes():
    patch = "@@ -1,3 +1,4 @@\n context\n-old\n+new\n+added\n context2"
    result = parse_patch(patch)
    # line 2 is the replacement, line 3 is the addition
    assert 2 in result
    assert 3 in result


def test_parse_empty_patch():
    assert parse_patch("") == {}


def test_parse_multiple_hunks():
    patch = "@@ -1,2 +1,2 @@\n-old1\n+new1\n ctx\n@@ -10,2 +10,3 @@\n ctx\n+added\n ctx"
    result = parse_patch(patch)
    assert 1 in result  # new1
    assert 11 in result  # added


def test_binary_file_detected():
    assert is_binary_or_skipped("image.png", "")
    assert is_binary_or_skipped("font.woff2", "")
    assert is_binary_or_skipped("data.bin", "Binary files a/data.bin and b/data.bin differ")


def test_code_file_not_skipped():
    assert not is_binary_or_skipped("main.py", "+hello")
    assert not is_binary_or_skipped("index.js", "+var x = 1;")


def test_parse_pr_files_removed_skipped():
    files = [{"filename": "deleted.py", "patch": "-old", "status": "removed"}]
    assert parse_pr_files(files) == []


def test_parse_pr_files_no_patch_skipped():
    files = [{"filename": "big.bin", "patch": "", "status": "modified"}]
    assert parse_pr_files(files) == []


def test_parse_pr_files_binary_skipped():
    files = [{"filename": "logo.png", "patch": "Binary files differ", "status": "added"}]
    assert parse_pr_files(files) == []


def test_parse_pr_files_valid():
    files = [
        {
            "filename": "app.py",
            "patch": "@@ -1,2 +1,3 @@\n ctx\n+new_line\n ctx",
            "status": "modified",
        }
    ]
    result = parse_pr_files(files)
    assert len(result) == 1
    assert result[0].path == "app.py"
    assert 2 in result[0].added_lines


def test_lock_file_skipped():
    # .lock extension check
    files2 = [{"filename": "poetry.lock", "patch": "+stuff", "status": "modified"}]
    assert parse_pr_files(files2) == []
