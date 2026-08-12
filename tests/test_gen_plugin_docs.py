import json

import pytest

from shipyard import gen_plugin_docs


def descriptor(root):
    return json.loads((root / "docs" / "plugin-docs.json").read_text())


def test_the_suite_block_is_projected_verbatim(tmp_path):
    (tmp_path / "plugin.yml").write_text("name: demo\nsuite: {gloss: a demo plugin}\n")

    gen_plugin_docs.run(tmp_path)

    assert descriptor(tmp_path)["gloss"] == "a demo plugin"


def test_a_plugin_with_no_suite_block_fails_loudly(tmp_path):
    (tmp_path / "plugin.yml").write_text("name: demo\n")

    with pytest.raises(SystemExit, match="no suite: block"):
        gen_plugin_docs.run(tmp_path)
