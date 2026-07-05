"""Tests for JavaScript (.js/.mjs/.cjs) extraction via the TypeScript grammar.

Also serves as the regression canary for tree-sitter core/grammar ABI
mismatches: core 0.26.0 with 0.23-era grammar wheels segfaulted on large,
expression-dense JavaScript files (found 2026-07-05 on real-world .mjs
sources). The large-file test below crashes the interpreter outright under
such a mismatch, which is exactly the signal we want in CI.
"""


import pytest

from projected_source.languages import get_extractor
from projected_source.languages.typescript import TypeScriptExtractor

SAMPLE_MJS = """\
import fs from "node:fs";
import { helper } from "./helper.mjs";

export async function handleSessionEnd(input) {
  const cwd = input.cwd || process.cwd();
  await helper(cwd);
  return cwd;
}

export function describeItem(state, item) {
  switch (item.type) {
    case "fileChange":
      return { message: `Applying ${item.changes.length} change(s).`, phase: "editing" };
    case "toolCall": {
      const summary =
        item.subagents.length > 0
          ? `Starting subagent ${item.subagents.join(", ")} via ${item.tool}.`
          : `Starting tool: ${item.tool}.`;
      return { message: summary, phase: "investigating" };
    }
    default:
      return null;
  }
}

class BrokerSession {
  constructor(endpoint) {
    this.endpoint = endpoint;
  }

  describe() {
    return `broker at ${this.endpoint}`;
  }
}

//@@start teardown-block
export function teardown(session) {
  session.close();
  return true;
}
//@@end teardown-block

const arrow = (x) => x * 2;
"""


@pytest.fixture
def mjs_file(tmp_path):
    path = tmp_path / "sample.mjs"
    path.write_text(SAMPLE_MJS)
    return path


@pytest.mark.parametrize("suffix", [".js", ".mjs", ".cjs"])
def test_get_extractor_supports_javascript(tmp_path, suffix):
    path = tmp_path / f"sample{suffix}"
    path.write_text(SAMPLE_MJS)
    extractor = get_extractor(path)
    assert isinstance(extractor, TypeScriptExtractor)


def test_extract_async_function(mjs_file):
    extractor = get_extractor(mjs_file)
    text, start, end = extractor.extract_function(mjs_file, "handleSessionEnd")
    assert "input.cwd || process.cwd()" in text
    assert start < end


def test_extract_function_with_switch_and_templates(mjs_file):
    extractor = get_extractor(mjs_file)
    text, _, _ = extractor.extract_function(mjs_file, "describeItem")
    assert "case \"toolCall\"" in text
    assert "Starting subagent" in text


def test_extract_marker_section(mjs_file):
    extractor = get_extractor(mjs_file)
    text, _, _ = extractor.extract_marker(mjs_file, "teardown-block")
    assert "session.close()" in text
    assert "//@@" not in text


def test_list_symbols_finds_functions_and_class(mjs_file):
    extractor = get_extractor(mjs_file)
    symbols = extractor.list_symbols(mjs_file)
    names = {s["name"] for s in symbols}
    assert "handleSessionEnd" in names
    assert "describeItem" in names


def test_large_expression_dense_file_does_not_crash(tmp_path):
    """Segfault canary: big JS files with switch/template/ternary density.

    Under a tree-sitter core/grammar ABI mismatch this crashed the process
    (SIGSEGV) rather than raising — so this test passing at all is the
    assertion that matters.
    """
    chunks = ["export function dispatch(item) {", "  switch (item.type) {"]
    for i in range(300):
        chunks.append(f'    case "kind{i}":')
        chunks.append(
            f"      return item.deep{i} != null "
            f'? `value ${{item.a{i}}} of ${{item.b{i}}}` '
            f': `fallback ${{item.c{i}}}`;'
        )
    chunks.append("    default: return null;")
    chunks.append("  }")
    chunks.append("}")
    for i in range(50):
        chunks.append(f"export async function worker{i}(input) {{")
        chunks.append(
            f"  const value = input?.nested?.deeper?.deepest{i} ?? "
            f'(input.alt ? `alt ${{input.x{i}}}` : null);'
        )
        chunks.append("  return { value, index: %d };" % i)
        chunks.append("}")

    path = tmp_path / "large.mjs"
    path.write_text("\n".join(chunks) + "\n")

    extractor = get_extractor(path)
    symbols = extractor.list_symbols(path)
    names = {s["name"] for s in symbols}
    assert "dispatch" in names
    assert "worker49" in names

    text, _, _ = extractor.extract_function(path, "worker25")
    assert "deepest25" in text
