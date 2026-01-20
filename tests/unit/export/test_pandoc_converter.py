"""
Tests for Pandoc Converter
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.export.pandoc_converter import PandocConverter, PYPANDOC_AVAILABLE


class TestPandocConverter:
    """Test PandocConverter."""

    def test_converter_initialization(self):
        """Test converter initialization."""
        converter = PandocConverter()
        assert converter is not None

    def test_check_pandoc_available_with_pypandoc(self):
        """Test check_pandoc_available when pypandoc is available."""
        converter = PandocConverter()
        
        if not PYPANDOC_AVAILABLE:
            pytest.skip("pypandoc not installed")
        
        with patch("src.export.pandoc_converter.pypandoc.get_pandoc_version") as mock_version:
            mock_version.return_value = "3.0.0"
            result = converter.check_pandoc_available()
            assert result is True

    def test_check_pandoc_available_without_pypandoc(self):
        """Test check_pandoc_available when pypandoc is not available."""
        with patch("src.export.pandoc_converter.PYPANDOC_AVAILABLE", False):
            converter = PandocConverter()
            result = converter.check_pandoc_available()
            assert result is False

    def test_check_pandoc_available_exception(self):
        """Test check_pandoc_available when get_pandoc_version raises exception."""
        if not PYPANDOC_AVAILABLE:
            pytest.skip("pypandoc not installed")
        
        converter = PandocConverter()
        with patch("src.export.pandoc_converter.pypandoc.get_pandoc_version") as mock_version:
            mock_version.side_effect = Exception("Pandoc not found")
            result = converter.check_pandoc_available()
            assert result is False

    def test_markdown_to_pdf_graceful_degradation(self, tmp_path):
        """Test graceful degradation when Pandoc not installed."""
        with patch("src.export.pandoc_converter.PYPANDOC_AVAILABLE", False):
            converter = PandocConverter()
            markdown_path = tmp_path / "test.md"
            markdown_path.write_text("# Test")
            output_path = tmp_path / "test.pdf"
            
            with pytest.raises(ImportError) as exc_info:
                converter.markdown_to_pdf(markdown_path, output_path)
            assert "pypandoc required" in str(exc_info.value)

    @pytest.mark.skipif(not PYPANDOC_AVAILABLE, reason="pypandoc not installed")
    def test_markdown_to_pdf_valid_input(self, tmp_path):
        """Test markdown_to_pdf with valid input."""
        converter = PandocConverter()
        markdown_path = tmp_path / "test.md"
        markdown_path.write_text("# Test Document\n\nThis is a test.")
        output_path = tmp_path / "test.pdf"
        
        with patch("src.export.pandoc_converter.pypandoc.convert_file") as mock_convert:
            mock_convert.return_value = None
            result = converter.markdown_to_pdf(markdown_path, output_path)
            assert result == output_path
            mock_convert.assert_called_once()
            assert "--citeproc" in mock_convert.call_args[1]["extra_args"]

    @pytest.mark.skipif(not PYPANDOC_AVAILABLE, reason="pypandoc not installed")
    def test_markdown_to_pdf_with_csl_style(self, tmp_path):
        """Test markdown_to_pdf with CSL style."""
        converter = PandocConverter()
        markdown_path = tmp_path / "test.md"
        markdown_path.write_text("# Test")
        output_path = tmp_path / "test.pdf"
        csl_style = tmp_path / "ieee.csl"
        csl_style.write_text("/* IEEE Style */")
        
        with patch("src.export.pandoc_converter.pypandoc.convert_file") as mock_convert:
            mock_convert.return_value = None
            converter.markdown_to_pdf(markdown_path, output_path, csl_style=csl_style)
            extra_args = mock_convert.call_args[1]["extra_args"]
            assert "--csl" in extra_args
            assert str(csl_style) in extra_args

    @pytest.mark.skipif(not PYPANDOC_AVAILABLE, reason="pypandoc not installed")
    def test_markdown_to_pdf_with_template(self, tmp_path):
        """Test markdown_to_pdf with template."""
        converter = PandocConverter()
        markdown_path = tmp_path / "test.md"
        markdown_path.write_text("# Test")
        output_path = tmp_path / "test.pdf"
        template = tmp_path / "template.latex"
        template.write_text("\\documentclass{article}")
        
        with patch("src.export.pandoc_converter.pypandoc.convert_file") as mock_convert:
            mock_convert.return_value = None
            converter.markdown_to_pdf(markdown_path, output_path, template=template)
            extra_args = mock_convert.call_args[1]["extra_args"]
            assert "--template" in extra_args
            assert str(template) in extra_args

    @pytest.mark.skipif(not PYPANDOC_AVAILABLE, reason="pypandoc not installed")
    def test_markdown_to_pdf_with_metadata(self, tmp_path):
        """Test markdown_to_pdf with metadata."""
        converter = PandocConverter()
        markdown_path = tmp_path / "test.md"
        markdown_path.write_text("# Test")
        output_path = tmp_path / "test.pdf"
        metadata = {"title": "Test Title", "author": "Test Author"}
        
        with patch("src.export.pandoc_converter.pypandoc.convert_file") as mock_convert:
            mock_convert.return_value = None
            converter.markdown_to_pdf(markdown_path, output_path, metadata=metadata)
            extra_args = mock_convert.call_args[1]["extra_args"]
            assert "-M" in extra_args
            assert "title=Test Title" in extra_args or "author=Test Author" in extra_args

    @pytest.mark.skipif(not PYPANDOC_AVAILABLE, reason="pypandoc not installed")
    def test_markdown_to_pdf_creates_directory(self, tmp_path):
        """Test markdown_to_pdf creates output directory."""
        converter = PandocConverter()
        markdown_path = tmp_path / "test.md"
        markdown_path.write_text("# Test")
        output_path = tmp_path / "subdir" / "test.pdf"
        
        with patch("src.export.pandoc_converter.pypandoc.convert_file") as mock_convert:
            mock_convert.return_value = None
            converter.markdown_to_pdf(markdown_path, output_path)
            assert output_path.parent.exists()

    @pytest.mark.skipif(not PYPANDOC_AVAILABLE, reason="pypandoc not installed")
    def test_markdown_to_pdf_error_handling(self, tmp_path):
        """Test error handling for PDF conversion failure."""
        converter = PandocConverter()
        markdown_path = tmp_path / "test.md"
        markdown_path.write_text("# Test")
        output_path = tmp_path / "test.pdf"
        
        with patch("src.export.pandoc_converter.pypandoc.convert_file") as mock_convert:
            mock_convert.side_effect = Exception("Conversion failed")
            with pytest.raises(RuntimeError) as exc_info:
                converter.markdown_to_pdf(markdown_path, output_path)
            assert "PDF conversion failed" in str(exc_info.value)

    @pytest.mark.skipif(not PYPANDOC_AVAILABLE, reason="pypandoc not installed")
    def test_markdown_to_pdf_missing_csl_style(self, tmp_path):
        """Test markdown_to_pdf with missing CSL style file."""
        converter = PandocConverter()
        markdown_path = tmp_path / "test.md"
        markdown_path.write_text("# Test")
        output_path = tmp_path / "test.pdf"
        csl_style = tmp_path / "nonexistent.csl"
        
        with patch("src.export.pandoc_converter.pypandoc.convert_file") as mock_convert:
            mock_convert.return_value = None
            # Should not include --csl if file doesn't exist
            converter.markdown_to_pdf(markdown_path, output_path, csl_style=csl_style)
            extra_args = mock_convert.call_args[1]["extra_args"]
            assert "--csl" not in extra_args or str(csl_style) not in extra_args

    @pytest.mark.skipif(not PYPANDOC_AVAILABLE, reason="pypandoc not installed")
    def test_markdown_to_pdf_missing_template(self, tmp_path):
        """Test markdown_to_pdf with missing template file."""
        converter = PandocConverter()
        markdown_path = tmp_path / "test.md"
        markdown_path.write_text("# Test")
        output_path = tmp_path / "test.pdf"
        template = tmp_path / "nonexistent.latex"
        
        with patch("src.export.pandoc_converter.pypandoc.convert_file") as mock_convert:
            mock_convert.return_value = None
            # Should not include --template if file doesn't exist
            converter.markdown_to_pdf(markdown_path, output_path, template=template)
            extra_args = mock_convert.call_args[1]["extra_args"]
            assert "--template" not in extra_args or str(template) not in extra_args

    @pytest.mark.skipif(not PYPANDOC_AVAILABLE, reason="pypandoc not installed")
    def test_markdown_to_docx_conversion(self, tmp_path):
        """Test markdown_to_docx conversion."""
        converter = PandocConverter()
        markdown_path = tmp_path / "test.md"
        markdown_path.write_text("# Test Document")
        output_path = tmp_path / "test.docx"
        
        with patch("src.export.pandoc_converter.pypandoc.convert_file") as mock_convert:
            mock_convert.return_value = None
            result = converter.markdown_to_docx(markdown_path, output_path)
            assert result == output_path
            mock_convert.assert_called_once()
            call_kwargs = mock_convert.call_args[1]
            assert call_kwargs["outputfile"] == str(output_path)
            assert "--citeproc" in call_kwargs["extra_args"]

    @pytest.mark.skipif(not PYPANDOC_AVAILABLE, reason="pypandoc not installed")
    def test_markdown_to_docx_with_csl_style(self, tmp_path):
        """Test markdown_to_docx with CSL style."""
        converter = PandocConverter()
        markdown_path = tmp_path / "test.md"
        markdown_path.write_text("# Test")
        output_path = tmp_path / "test.docx"
        csl_style = tmp_path / "ieee.csl"
        csl_style.write_text("/* IEEE Style */")
        
        with patch("src.export.pandoc_converter.pypandoc.convert_file") as mock_convert:
            mock_convert.return_value = None
            converter.markdown_to_docx(markdown_path, output_path, csl_style=csl_style)
            extra_args = mock_convert.call_args[1]["extra_args"]
            assert "--csl" in extra_args

    @pytest.mark.skipif(not PYPANDOC_AVAILABLE, reason="pypandoc not installed")
    def test_markdown_to_docx_error_handling(self, tmp_path):
        """Test error handling for DOCX conversion failure."""
        converter = PandocConverter()
        markdown_path = tmp_path / "test.md"
        markdown_path.write_text("# Test")
        output_path = tmp_path / "test.docx"
        
        with patch("src.export.pandoc_converter.pypandoc.convert_file") as mock_convert:
            mock_convert.side_effect = Exception("Conversion failed")
            with pytest.raises(RuntimeError) as exc_info:
                converter.markdown_to_docx(markdown_path, output_path)
            assert "DOCX conversion failed" in str(exc_info.value)

    @pytest.mark.skipif(not PYPANDOC_AVAILABLE, reason="pypandoc not installed")
    def test_markdown_to_html_conversion(self, tmp_path):
        """Test markdown_to_html conversion."""
        converter = PandocConverter()
        markdown_path = tmp_path / "test.md"
        markdown_path.write_text("# Test Document")
        output_path = tmp_path / "test.html"
        
        with patch("src.export.pandoc_converter.pypandoc.convert_file") as mock_convert:
            mock_convert.return_value = None
            result = converter.markdown_to_html(markdown_path, output_path)
            assert result == output_path
            mock_convert.assert_called_once()
            call_kwargs = mock_convert.call_args[1]
            assert call_kwargs["outputfile"] == str(output_path)
            assert "--citeproc" in call_kwargs["extra_args"]

    @pytest.mark.skipif(not PYPANDOC_AVAILABLE, reason="pypandoc not installed")
    def test_markdown_to_html_standalone(self, tmp_path):
        """Test markdown_to_html with standalone flag."""
        converter = PandocConverter()
        markdown_path = tmp_path / "test.md"
        markdown_path.write_text("# Test")
        output_path = tmp_path / "test.html"
        
        with patch("src.export.pandoc_converter.pypandoc.convert_file") as mock_convert:
            mock_convert.return_value = None
            converter.markdown_to_html(markdown_path, output_path, standalone=True)
            extra_args = mock_convert.call_args[1]["extra_args"]
            assert "--standalone" in extra_args

    @pytest.mark.skipif(not PYPANDOC_AVAILABLE, reason="pypandoc not installed")
    def test_markdown_to_html_not_standalone(self, tmp_path):
        """Test markdown_to_html without standalone flag."""
        converter = PandocConverter()
        markdown_path = tmp_path / "test.md"
        markdown_path.write_text("# Test")
        output_path = tmp_path / "test.html"
        
        with patch("src.export.pandoc_converter.pypandoc.convert_file") as mock_convert:
            mock_convert.return_value = None
            converter.markdown_to_html(markdown_path, output_path, standalone=False)
            extra_args = mock_convert.call_args[1]["extra_args"]
            assert "--standalone" not in extra_args

    @pytest.mark.skipif(not PYPANDOC_AVAILABLE, reason="pypandoc not installed")
    def test_markdown_to_html_error_handling(self, tmp_path):
        """Test error handling for HTML conversion failure."""
        converter = PandocConverter()
        markdown_path = tmp_path / "test.md"
        markdown_path.write_text("# Test")
        output_path = tmp_path / "test.html"
        
        with patch("src.export.pandoc_converter.pypandoc.convert_file") as mock_convert:
            mock_convert.side_effect = Exception("Conversion failed")
            with pytest.raises(RuntimeError) as exc_info:
                converter.markdown_to_html(markdown_path, output_path)
            assert "HTML conversion failed" in str(exc_info.value)

    @pytest.mark.skipif(not PYPANDOC_AVAILABLE, reason="pypandoc not installed")
    def test_conversion_with_special_characters(self, tmp_path):
        """Test conversion with special characters in markdown."""
        converter = PandocConverter()
        markdown_path = tmp_path / "test.md"
        markdown_path.write_text("# Test & Special Characters\n\n< > & \" '")
        output_path = tmp_path / "test.pdf"
        
        with patch("src.export.pandoc_converter.pypandoc.convert_file") as mock_convert:
            mock_convert.return_value = None
            converter.markdown_to_pdf(markdown_path, output_path)
            mock_convert.assert_called_once()

    @pytest.mark.skipif(not PYPANDOC_AVAILABLE, reason="pypandoc not installed")
    def test_conversion_with_citations(self, tmp_path):
        """Test conversion with citations in markdown."""
        converter = PandocConverter()
        markdown_path = tmp_path / "test.md"
        markdown_path.write_text("# Test\n\nThis is a citation [@doi:10.1038/nbt.3780].")
        output_path = tmp_path / "test.pdf"
        csl_style = tmp_path / "ieee.csl"
        csl_style.write_text("/* IEEE Style */")
        
        with patch("src.export.pandoc_converter.pypandoc.convert_file") as mock_convert:
            mock_convert.return_value = None
            converter.markdown_to_pdf(markdown_path, output_path, csl_style=csl_style)
            extra_args = mock_convert.call_args[1]["extra_args"]
            assert "--citeproc" in extra_args
            assert "--csl" in extra_args
