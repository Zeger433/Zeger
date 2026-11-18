import asyncio, os, tempfile
os.environ["WORKSPACE_DIR"] = tempfile.mkdtemp()
import pytest
import tools


def use(name, **args):
    return asyncio.run(tools.run_tool(name, args))[0]


def test_write_edit_read():
    use("write_file", path="a/b.txt", content="one two")
    use("edit_file", path="a/b.txt", old_str="two", new_str="2")
    assert use("read_file", path="a/b.txt") == "one 2"


def test_edit_needs_exactly_one_match():
    use("write_file", path="dup.txt", content="x x")
    with pytest.raises(ValueError):
        use("edit_file", path="dup.txt", old_str="x", new_str="y")


@pytest.mark.parametrize("path", ["../etc/passwd", "/etc/passwd", "a/../../x"])
def test_paths_cannot_leave_workspace(path):
    with pytest.raises(ValueError):
        use("read_file", path=path)
