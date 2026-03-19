"""Tests for TypeScript extraction."""

from pathlib import Path

import pytest

from projected_source.languages import get_extractor
from projected_source.languages.typescript import TypeScriptExtractor

SAMPLE_TS = """\
export function processData(input: string): number {
    return input.length;
}

export const MAX_SIZE: number = 100;

interface Config {
    host: string;
    port: number;
}

class Handler {
    private name: string;

    constructor(name: string) {
        this.name = name;
    }

    process(data: Config): void {
        console.log(data.host);
    }
}

enum Status {
    Active = 1,
    Inactive = 2,
}

type Result<T> = { data: T; error?: string };

const arrow = (x: number): number => x * 2;

//@@start example-section
const a = 1;
const b = 2;
//@@end example-section
"""


class TestTypeScriptExtractorFunctions:
    def test_extract_exported_function(self, tmp_path):
        f = tmp_path / "test.ts"
        f.write_text(SAMPLE_TS)
        ext = TypeScriptExtractor()
        text, start, end = ext.extract_function(f, "processData")
        assert "export function processData" in text
        assert "return input.length" in text

    def test_extract_arrow_function(self, tmp_path):
        f = tmp_path / "test.ts"
        f.write_text(SAMPLE_TS)
        ext = TypeScriptExtractor()
        text, start, end = ext.extract_variable(f, "arrow")
        assert "const arrow" in text
        assert "x * 2" in text

    def test_extract_method(self, tmp_path):
        f = tmp_path / "test.ts"
        f.write_text(SAMPLE_TS)
        ext = TypeScriptExtractor()
        text, start, end = ext.extract_function(f, "Handler.process")
        assert "process(data: Config)" in text
        assert "console.log" in text

    def test_extract_constructor(self, tmp_path):
        f = tmp_path / "test.ts"
        f.write_text(SAMPLE_TS)
        ext = TypeScriptExtractor()
        text, start, end = ext.extract_function(f, "Handler.constructor")
        assert "constructor(name: string)" in text

    def test_function_not_found(self, tmp_path):
        f = tmp_path / "test.ts"
        f.write_text(SAMPLE_TS)
        ext = TypeScriptExtractor()
        with pytest.raises(ValueError, match="not found"):
            ext.extract_function(f, "nonExistent")


class TestTypeScriptExtractorStructs:
    def test_extract_class(self, tmp_path):
        f = tmp_path / "test.ts"
        f.write_text(SAMPLE_TS)
        ext = TypeScriptExtractor()
        text, start, end = ext.extract_struct(f, "Handler")
        assert "class Handler" in text
        assert "process(data: Config)" in text

    def test_extract_interface(self, tmp_path):
        f = tmp_path / "test.ts"
        f.write_text(SAMPLE_TS)
        ext = TypeScriptExtractor()
        text, start, end = ext.extract_struct(f, "Config")
        assert "interface Config" in text
        assert "host: string" in text

    def test_extract_type_alias(self, tmp_path):
        f = tmp_path / "test.ts"
        f.write_text(SAMPLE_TS)
        ext = TypeScriptExtractor()
        text, start, end = ext.extract_struct(f, "Result")
        assert "type Result" in text

    def test_extract_enum(self, tmp_path):
        f = tmp_path / "test.ts"
        f.write_text(SAMPLE_TS)
        ext = TypeScriptExtractor()
        text, start, end = ext.extract_enum(f, "Status")
        assert "enum Status" in text
        assert "Active = 1" in text

    def test_struct_not_found(self, tmp_path):
        f = tmp_path / "test.ts"
        f.write_text(SAMPLE_TS)
        ext = TypeScriptExtractor()
        with pytest.raises(ValueError, match="not found"):
            ext.extract_struct(f, "NonExistent")


class TestTypeScriptExtractorVariables:
    def test_extract_const(self, tmp_path):
        f = tmp_path / "test.ts"
        f.write_text(SAMPLE_TS)
        ext = TypeScriptExtractor()
        text, start, end = ext.extract_variable(f, "MAX_SIZE")
        assert "MAX_SIZE" in text
        assert "100" in text

    def test_variable_not_found(self, tmp_path):
        f = tmp_path / "test.ts"
        f.write_text(SAMPLE_TS)
        ext = TypeScriptExtractor()
        with pytest.raises(ValueError, match="not found"):
            ext.extract_variable(f, "NONEXISTENT")


class TestTypeScriptExtractorMarkers:
    def test_extract_marker(self, tmp_path):
        f = tmp_path / "test.ts"
        f.write_text(SAMPLE_TS)
        ext = TypeScriptExtractor()
        text, start, end = ext.extract_marker(f, "example-section")
        assert "const a = 1" in text
        assert "const b = 2" in text

    def test_marker_not_found(self, tmp_path):
        f = tmp_path / "test.ts"
        f.write_text(SAMPLE_TS)
        ext = TypeScriptExtractor()
        with pytest.raises(ValueError, match="not found"):
            ext.extract_marker(f, "nonexistent")


class TestTypeScriptListSymbols:
    def test_lists_all_symbols(self, tmp_path):
        f = tmp_path / "test.ts"
        f.write_text(SAMPLE_TS)
        ext = TypeScriptExtractor()
        symbols = ext.list_symbols(f)
        names = [s["name"] for s in symbols]
        assert "processData" in names
        assert "MAX_SIZE" in names
        assert "Config" in names
        assert "Handler" in names
        assert "Handler.constructor" in names
        assert "Handler.process" in names
        assert "Status" in names
        assert "Result" in names
        assert "arrow" in names
        assert "example-section" in names

    def test_symbol_params(self, tmp_path):
        f = tmp_path / "test.ts"
        f.write_text(SAMPLE_TS)
        ext = TypeScriptExtractor()
        symbols = ext.list_symbols(f)
        by_name = {s["name"]: s for s in symbols}
        assert by_name["processData"]["param"] == "function"
        assert by_name["Handler"]["param"] == "struct"
        assert by_name["Config"]["param"] == "struct"
        assert by_name["Status"]["param"] == "enum"
        assert by_name["MAX_SIZE"]["param"] == "var"
        assert by_name["Handler.process"]["param"] == "function"


class TestTypeScriptRegistry:
    def test_ts_extension(self):
        ext = get_extractor(Path("test.ts"))
        assert isinstance(ext, TypeScriptExtractor)

    def test_tsx_extension(self):
        ext = get_extractor(Path("test.tsx"))
        assert isinstance(ext, TypeScriptExtractor)
        assert ext._tsx is True

    def test_mts_extension(self):
        ext = get_extractor(Path("test.mts"))
        assert isinstance(ext, TypeScriptExtractor)


class TestTypeScriptRendererIntegration:
    def test_code_function_typescript(self, tmp_path):
        from projected_source.core.renderer import TemplateRenderer

        ts_file = tmp_path / "example.ts"
        ts_file.write_text("export function hello(): string {\n    return 'hi';\n}\n")

        renderer = TemplateRenderer(template_dir=tmp_path, repo_path=tmp_path)
        result = renderer._code_function("example.ts", function="hello", github=False)
        assert "export function hello()" in result
        assert "return 'hi'" in result
        assert "```typescript" in result
