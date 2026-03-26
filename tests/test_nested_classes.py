"""Tests for nested class extraction in C++ (PIMPL pattern, etc.)."""

from pathlib import Path

import pytest

from projected_source.languages.cpp import CppExtractor

FIXTURE = Path(__file__).parent / "fixtures" / "cpp" / "nested_classes.cpp"


class TestNestedClassSymbolDiscovery:
    """list_symbols should find all nested classes and their members."""

    @pytest.fixture
    def symbols(self):
        ext = CppExtractor()
        return ext.list_symbols(FIXTURE)

    @pytest.fixture
    def symbol_names(self, symbols):
        return [s["name"] for s in symbols]

    def test_finds_top_level_class(self, symbol_names):
        assert "BeastResponseAdapter" in symbol_names

    def test_finds_pimpl_class(self, symbol_names):
        assert "HttpServer::Impl" in symbol_names

    def test_finds_nested_session_class(self, symbol_names):
        assert "HttpServer::Impl::Session" in symbol_names

    def test_finds_pimpl_methods(self, symbol_names):
        assert "HttpServer::Impl::accept" in symbol_names
        assert "HttpServer::Impl::run" in symbol_names
        assert "HttpServer::Impl::stop" in symbol_names

    def test_finds_nested_session_methods(self, symbol_names):
        assert "HttpServer::Impl::Session::start" in symbol_names
        assert "HttpServer::Impl::Session::read" in symbol_names
        assert "HttpServer::Impl::Session::process_request" in symbol_names
        assert "HttpServer::Impl::Session::write" in symbol_names

    def test_finds_pimpl_constructor(self, symbol_names):
        assert "HttpServer::Impl::Impl" in symbol_names

    def test_finds_marker(self, symbol_names):
        assert "beast-session" in symbol_names


class TestNestedClassExtraction:
    """Extract specific nested classes and methods."""

    def test_extract_pimpl_class(self):
        ext = CppExtractor()
        text, start, end = ext.extract_struct(FIXTURE, "HttpServer::Impl")
        assert "class HttpServer::Impl" in text
        assert "class Session" in text
        assert "accept()" in text

    def test_extract_nested_session(self):
        ext = CppExtractor()
        text, start, end = ext.extract_struct(FIXTURE, "HttpServer::Impl::Session")
        assert "class Session" in text
        assert "start()" in text
        assert "read()" in text

    def test_extract_pimpl_method(self):
        ext = CppExtractor()
        text, start, end = ext.extract_function(FIXTURE, "HttpServer::Impl::accept")
        assert "accept()" in text
        assert "async_accept" in text

    def test_extract_nested_method(self):
        ext = CppExtractor()
        text, start, end = ext.extract_function(FIXTURE, "HttpServer::Impl::Session::read")
        assert "read()" in text
        assert "async_read" in text

    def test_extract_pimpl_constructor(self):
        ext = CppExtractor()
        text, start, end = ext.extract_function(FIXTURE, "HttpServer::Impl::Impl")
        assert "Impl(" in text
        assert "handler" in text

    def test_extract_marker_in_pimpl(self):
        ext = CppExtractor()
        text, start, end = ext.extract_marker(FIXTURE, "beast-session")
        assert "class Session" in text
        assert "start()" in text

    def test_extract_top_level_methods_still_work(self):
        ext = CppExtractor()
        text, start, end = ext.extract_function(FIXTURE, "BeastResponseAdapter::setStatus")
        assert "setStatus" in text
        assert "result" in text
