"""Tests for Rust extraction."""

from pathlib import Path

import pytest

from projected_source.languages import get_extractor
from projected_source.languages.rust import RustExtractor

SAMPLE_RUST = """\
use std::collections::HashMap;

pub const MAX_SIZE: usize = 100;
static GREETING: &str = "hello";

pub struct Handler {
    name: String,
    count: i32,
}

pub struct Tup(i32, u8);

pub struct Empty;

impl Handler {
    pub fn new(name: String) -> Self {
        Handler { name, count: 0 }
    }

    pub fn process(&mut self, items: &[String]) {
        for item in items {
            println!("{}", item);
        }
    }

    fn private_helper(&self) -> i32 {
        42
    }
}

pub trait Service {
    fn start(&self);
    fn stop(&self) {
        // default impl
    }
}

impl Service for Handler {
    fn start(&self) {
        println!("starting");
    }
}

pub enum Status {
    Active,
    Inactive(String),
    Pending { reason: String },
}

pub union Data {
    a: i32,
    b: f32,
}

pub type Alias = i32;

pub fn free_function(x: i32) -> i32 {
    x + 1
}

//@@start example-section
let a = 1;
let b = 2;
//@@end example-section
"""


@pytest.fixture
def rust_file(tmp_path) -> Path:
    f = tmp_path / "sample.rs"
    f.write_text(SAMPLE_RUST)
    return f


class TestRustExtractorFunctions:
    def test_extract_free_function(self, rust_file):
        ext = RustExtractor()
        text, start, end = ext.extract_function(rust_file, "free_function")
        assert "pub fn free_function" in text
        assert start < end

    def test_extract_qualified_method(self, rust_file):
        ext = RustExtractor()
        text, _, _ = ext.extract_function(rust_file, "Handler.process")
        assert "fn process" in text
        assert "for item in items" in text

    def test_extract_method_with_double_colon(self, rust_file):
        ext = RustExtractor()
        text, _, _ = ext.extract_function(rust_file, "Handler::new")
        assert "fn new(name: String)" in text

    def test_extract_method_unqualified(self, rust_file):
        ext = RustExtractor()
        text, _, _ = ext.extract_function(rust_file, "private_helper")
        assert "fn private_helper" in text

    def test_extract_trait_impl_method(self, rust_file):
        """Methods inside `impl Trait for Type` should resolve via Type.method."""
        ext = RustExtractor()
        text, _, _ = ext.extract_function(rust_file, "Handler.start")
        assert 'println!("starting")' in text

    def test_extract_trait_method(self, rust_file):
        """Methods declared on a trait should resolve via Trait.method."""
        ext = RustExtractor()
        text, _, _ = ext.extract_function(rust_file, "Service.stop")
        assert "fn stop" in text
        assert "default impl" in text

    def test_missing_function_raises(self, rust_file):
        ext = RustExtractor()
        with pytest.raises(ValueError, match="not found"):
            ext.extract_function(rust_file, "nonexistent")


class TestRustExtractorStructs:
    def test_extract_struct(self, rust_file):
        ext = RustExtractor()
        text, _, _ = ext.extract_struct(rust_file, "Handler")
        assert "pub struct Handler" in text
        assert "name: String" in text

    def test_extract_tuple_struct(self, rust_file):
        ext = RustExtractor()
        text, _, _ = ext.extract_struct(rust_file, "Tup")
        assert "pub struct Tup(i32, u8);" in text

    def test_extract_unit_struct(self, rust_file):
        ext = RustExtractor()
        text, _, _ = ext.extract_struct(rust_file, "Empty")
        assert "pub struct Empty" in text

    def test_extract_enum(self, rust_file):
        ext = RustExtractor()
        text, _, _ = ext.extract_enum(rust_file, "Status")
        assert "pub enum Status" in text
        assert "Active" in text
        assert "Pending { reason: String }" in text

    def test_extract_union(self, rust_file):
        ext = RustExtractor()
        text, _, _ = ext.extract_struct(rust_file, "Data")
        assert "pub union Data" in text

    def test_extract_trait(self, rust_file):
        ext = RustExtractor()
        text, _, _ = ext.extract_struct(rust_file, "Service")
        assert "pub trait Service" in text
        assert "fn start" in text

    def test_extract_type_alias(self, rust_file):
        ext = RustExtractor()
        text, _, _ = ext.extract_struct(rust_file, "Alias")
        assert "pub type Alias = i32;" in text


class TestRustExtractorVariables:
    def test_extract_const(self, rust_file):
        ext = RustExtractor()
        text, _, _ = ext.extract_variable(rust_file, "MAX_SIZE")
        assert "pub const MAX_SIZE: usize = 100;" in text

    def test_extract_static(self, rust_file):
        ext = RustExtractor()
        text, _, _ = ext.extract_variable(rust_file, "GREETING")
        assert 'static GREETING: &str = "hello";' in text

    def test_missing_variable_raises(self, rust_file):
        ext = RustExtractor()
        with pytest.raises(ValueError, match="not found"):
            ext.extract_variable(rust_file, "nonexistent")


class TestRustExtractorMarkers:
    def test_extract_file_marker(self, rust_file):
        ext = RustExtractor()
        text, _, _ = ext.extract_marker(rust_file, "example-section")
        assert "let a = 1;" in text
        assert "let b = 2;" in text

    def test_extract_marker_inside_function(self, tmp_path):
        src = """\
fn worker() {
    let outer = 1;
    //@@start inner
    let payload = compute();
    process(payload);
    //@@end inner
    let after = 2;
}
"""
        f = tmp_path / "marker.rs"
        f.write_text(src)
        ext = RustExtractor()
        text, _, _ = ext.extract_function_marker(f, "worker", "inner")
        assert "let payload = compute();" in text
        assert "process(payload);" in text
        assert "let outer" not in text


class TestRustExtractorListSymbols:
    def test_lists_top_level_and_methods(self, rust_file):
        ext = RustExtractor()
        symbols = ext.list_symbols(rust_file)
        names = {s["name"] for s in symbols}

        # Free items
        assert "free_function" in names
        assert "MAX_SIZE" in names
        assert "GREETING" in names
        assert "Handler" in names
        assert "Status" in names
        assert "Data" in names
        assert "Service" in names
        assert "Alias" in names

        # Methods from inherent and trait impls
        assert "Handler.new" in names
        assert "Handler.process" in names
        assert "Handler.private_helper" in names
        assert "Handler.start" in names

        # Trait-declared methods
        assert "Service.start" in names
        assert "Service.stop" in names

        # Marker
        assert "example-section" in names

    def test_kind_metadata(self, rust_file):
        ext = RustExtractor()
        by_name = {s["name"]: s for s in ext.list_symbols(rust_file)}
        assert by_name["Handler"]["kind"] == "struct"
        assert by_name["Status"]["kind"] == "enum"
        assert by_name["Data"]["kind"] == "union"
        assert by_name["Service"]["kind"] == "trait"
        assert by_name["Alias"]["kind"] == "type"
        assert by_name["MAX_SIZE"]["kind"] == "const"
        assert by_name["GREETING"]["kind"] == "static"
        assert by_name["free_function"]["kind"] == "function"
        assert by_name["Handler.new"]["kind"] == "method"


class TestRustExtractorRegistration:
    def test_get_extractor_for_rs(self, tmp_path):
        f = tmp_path / "x.rs"
        f.write_text("fn main() {}")
        ext = get_extractor(f)
        assert isinstance(ext, RustExtractor)


# ---------------------------------------------------------------------------
# Issue #1 — leading attributes (derives, cfg, inline) included in extraction.
# ---------------------------------------------------------------------------

ATTR_RUST = """\
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
pub struct Key(pub [u8; 32]);

#[derive(Clone, Debug)]
pub enum Status {
    Ok,
    Bad(String),
}

#[inline]
#[must_use]
pub fn helper(x: i32) -> i32 {
    x + 1
}

#[derive(Default)]
pub struct Container {
    val: i32,
}

impl Container {
    #[inline(always)]
    pub fn fast(&self) -> i32 {
        self.val
    }
}

#[cfg(target_os = "linux")]
pub const LINUX_ONLY: u32 = 1;
"""


@pytest.fixture
def attr_file(tmp_path) -> Path:
    f = tmp_path / "attrs.rs"
    f.write_text(ATTR_RUST)
    return f


class TestRustExtractorAttributes:
    def test_struct_includes_derives(self, attr_file):
        ext = RustExtractor()
        text, start, end = ext.extract_struct(attr_file, "Key")
        assert "#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]" in text
        assert '#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]' in text
        assert "pub struct Key(pub [u8; 32]);" in text
        assert start == 1  # First derive line
        assert end == 3

    def test_enum_includes_derives(self, attr_file):
        ext = RustExtractor()
        text, _, _ = ext.extract_struct(attr_file, "Status")
        assert "#[derive(Clone, Debug)]" in text
        assert "pub enum Status" in text

    def test_function_includes_attributes(self, attr_file):
        ext = RustExtractor()
        text, _, _ = ext.extract_function(attr_file, "helper")
        assert "#[inline]" in text
        assert "#[must_use]" in text
        assert "pub fn helper(x: i32) -> i32" in text

    def test_method_inside_impl_includes_its_attribute(self, attr_file):
        ext = RustExtractor()
        text, _, _ = ext.extract_function(attr_file, "Container.fast")
        assert "#[inline(always)]" in text
        assert "pub fn fast(&self) -> i32" in text

    def test_const_includes_cfg_attribute(self, attr_file):
        ext = RustExtractor()
        text, _, _ = ext.extract_variable(attr_file, "LINUX_ONLY")
        assert '#[cfg(target_os = "linux")]' in text
        assert "pub const LINUX_ONLY: u32 = 1;" in text


# ---------------------------------------------------------------------------
# Issue #2 — extracted impl-block bodies are dedented uniformly.
# ---------------------------------------------------------------------------

INDENT_RUST = """\
pub struct Foo {
    val: i32,
}

impl Foo {
    pub fn fetch(&self, hash: &[u8; 32]) -> std::io::Result<Option<Vec<u8>>> {
        let result = self.inner.fetch(hash);
        self.stats.note_fetch_result(&result);
        result
    }
}
"""


class TestRustExtractorIndentation:
    def test_method_extraction_is_dedented(self, tmp_path):
        f = tmp_path / "indent.rs"
        f.write_text(INDENT_RUST)
        ext = RustExtractor()
        text, _, _ = ext.extract_function(f, "Foo.fetch")
        lines = text.splitlines()
        # Signature is at column 0
        assert lines[0].startswith("pub fn fetch(")
        # Body has exactly 4 spaces of indent (one level inside the fn) — not 8.
        body_line = next(line for line in lines if "let result" in line)
        assert body_line.startswith("    let result"), f"expected 4-space body, got {body_line!r}"
        # Closing brace at column 0
        assert lines[-1] == "}"

    def test_marker_inside_indented_function_is_dedented(self, tmp_path):
        src = """\
mod outer {
    fn worker() {
        let x = 1;
        //@@start core
        let y = compute(x);
        process(y);
        //@@end core
    }
}
"""
        f = tmp_path / "marker_indent.rs"
        f.write_text(src)
        ext = RustExtractor()
        text, _, _ = ext.extract_function_marker(f, "worker", "core")
        lines = text.splitlines()
        # Marker body should be dedented to column 0
        assert lines[0] == "let y = compute(x);"
        assert lines[1] == "process(y);"


# ---------------------------------------------------------------------------
# Issue #3 — items in #[cfg(test)] mod tests { ... } visible only with opt-in.
# ---------------------------------------------------------------------------

CFG_TEST_RUST = """\
pub fn add(a: i32, b: i32) -> i32 {
    a + b
}

pub mod helpers {
    pub fn shared_util() -> i32 {
        7
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_add() {
        assert_eq!(add(2, 3), 5);
    }

    fn fixture_key(n: u8) -> [u8; 32] {
        let mut k = [0u8; 32];
        k[0] = n;
        k
    }
}
"""


@pytest.fixture
def cfg_test_file(tmp_path) -> Path:
    f = tmp_path / "cfg_test.rs"
    f.write_text(CFG_TEST_RUST)
    return f


class TestRustExtractorCfgTest:
    def test_cfg_test_hidden_by_default(self, cfg_test_file):
        ext = RustExtractor()
        names = {s["name"] for s in ext.list_symbols(cfg_test_file)}
        assert "add" in names
        # Non-test modules are recursed into by default
        assert "helpers::shared_util" in names
        # Test module contents are NOT shown by default
        assert "tests::test_add" not in names
        assert "tests::fixture_key" not in names

    def test_cfg_test_visible_with_include_tests(self, cfg_test_file):
        ext = RustExtractor()
        names = {s["name"] for s in ext.list_symbols(cfg_test_file, include_tests=True)}
        assert "tests::test_add" in names
        assert "tests::fixture_key" in names

    def test_extract_function_finds_test_function(self, cfg_test_file):
        """Direct extraction should still work — the user named the symbol explicitly."""
        ext = RustExtractor()
        text, _, _ = ext.extract_function(cfg_test_file, "test_add")
        assert "fn test_add" in text
        assert "assert_eq!(add(2, 3), 5);" in text

    def test_extract_function_finds_helper_in_module(self, cfg_test_file):
        ext = RustExtractor()
        text, _, _ = ext.extract_function(cfg_test_file, "shared_util")
        assert "fn shared_util" in text


# ---------------------------------------------------------------------------
# Issue #4 — GitHub permalinks for dirty files are flagged.
# ---------------------------------------------------------------------------


class TestGitHubDirtyPermalink:
    def test_dirty_file_permalink_is_flagged(self, tmp_path, monkeypatch):
        from projected_source.core.github import GitHubIntegration

        gh = GitHubIntegration(repo_path=tmp_path)
        # Force a known github URL/commit and a dirty result.
        monkeypatch.setattr(gh, "_init_repo_info", lambda: None)
        gh._initialized = True
        gh._github_url = "https://github.com/example/repo"
        gh._commit_hash = "deadbeef"
        monkeypatch.setattr(gh, "is_file_dirty", lambda _p: True)
        monkeypatch.setattr(gh, "map_to_committed_line", lambda _p, line: line)
        # Tracked-but-modified: the file DOES exist at HEAD, so the link is kept.
        # (An untracked file, where exists_at_commit is False, is suppressed
        # instead — see test_github_permalinks.py.)
        monkeypatch.setattr(gh, "exists_at_commit", lambda _p, _c: True)

        result = gh.get_permalink(tmp_path / "src" / "x.rs", start_line=10, end_line=20)
        assert "*(uncommitted)*" in result
        assert "deadbeef" in result

    def test_clean_file_permalink_has_no_dirty_marker(self, tmp_path, monkeypatch):
        from projected_source.core.github import GitHubIntegration

        gh = GitHubIntegration(repo_path=tmp_path)
        monkeypatch.setattr(gh, "_init_repo_info", lambda: None)
        gh._initialized = True
        gh._github_url = "https://github.com/example/repo"
        gh._commit_hash = "deadbeef"
        monkeypatch.setattr(gh, "is_file_dirty", lambda _p: False)
        monkeypatch.setattr(gh, "map_to_committed_line", lambda _p, line: line)

        result = gh.get_permalink(tmp_path / "src" / "x.rs", start_line=10, end_line=20)
        assert "uncommitted" not in result
