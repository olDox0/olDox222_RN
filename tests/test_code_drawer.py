from engine.tools.code_drawer import CodeDrawer


def test_code_drawer_upsert_and_get(tmp_path) -> None:
    drawer = CodeDrawer(store_path=tmp_path / "drawer.json")
    saved = drawer.upsert_snippet(
        name="quicksort",
        lang="python",
        inputs=["list[int]"],
        outputs=["list[int]"],
        code="def quicksort(x):\n    return sorted(x)\n",
        tags=["sort"],
    )

    assert saved.name == "quicksort"
    loaded = drawer.get(name="quicksort", lang="python")
    assert loaded is not None
    assert "def quicksort" in loaded.code


def test_code_drawer_assemble_scores_name_and_io(tmp_path) -> None:
    drawer = CodeDrawer(store_path=tmp_path / "drawer.json")
    drawer.upsert_snippet(
        name="quicksort",
        lang="python",
        inputs=["list[int]"],
        outputs=["list[int]"],
        code="def quicksort(x):\n    return sorted(x)\n",
        tags=[],
    )
    drawer.upsert_snippet(
        name="partition",
        lang="python",
        inputs=["list[int]"],
        outputs=["tuple[list[int],int,list[int]]"],
        code="def partition(x):\n    return [],0,[]\n",
        tags=[],
    )

    assembled = drawer.assemble(
        name="quicksort",
        lang="python",
        inputs=["list[int]"],
        outputs=["list[int]"],
    )
    assert assembled is not None
    assert assembled.name == "quicksort"


def test_code_drawer_save_from_context_extracts_code_blocks(tmp_path) -> None:
    drawer = CodeDrawer(store_path=tmp_path / "drawer.json")
    context = """
[CTX-BEGIN]
scope: test
[CODE-BEGIN]
def quicksort(x):
    return sorted(x)
[CODE-END]
[CTX-END]
"""
    saved = drawer.save_from_context(
        name="quicksort",
        lang="python",
        context=context,
        tags=["crawler"],
    )
    assert saved == 1
    got = drawer.get(name="quicksort", lang="python")
    assert got is not None
    assert "def quicksort" in got.code
