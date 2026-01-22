# Troubleshooting Guide

Detailed troubleshooting guide for common issues.

## Table of Contents

- [Common Issues](#common-issues)
- [API Key Issues](#api-key-issues)
- [Database Connection Issues](#database-connection-issues)
- [Workflow Execution Issues](#workflow-execution-issues)
- [Export and Formatting Issues](#export-and-formatting-issues)

## Common Issues

### "No papers found"

- Check search query is not too specific
- Verify databases are enabled in `config/workflow.yaml`
- Test database connectors: `python scripts/test_database_health.py`

### "ACM 403 Forbidden Error"

- ACM Digital Library may block automated access
- The system automatically handles 403 errors gracefully by skipping ACM searches
- No action needed - workflow continues with other databases
- This is expected behavior and does not indicate a system error

## API Key Issues

### "LLM API Error"

- Verify LLM API key is set (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, etc.)
- Check API key is valid and has credits
- Try a different LLM provider
- For quality assessment auto-fill, ensure `GEMINI_API_KEY` is set (default LLM provider)

### "Quality assessment auto-fill failed"

- Verify `GEMINI_API_KEY` is set in environment
- Check API key has sufficient credits
- Review logs for specific error messages
- If auto-fill fails, the workflow falls back to manual assessment
- Use `--no-auto-fill-qa` to disable auto-fill and complete assessments manually

### "Rate limit exceeded"

- Wait a few minutes and retry
- Set API keys for higher rate limits
- Enable caching to reduce API calls

## Database Connection Issues

### "Pydantic validation error for methodology field"

- Fixed in latest version - methodology field is now optional
- If you see validation errors, ensure you're using the latest code
- The system now correctly handles `null` values for optional fields

### "SSL Certificate Errors" (CERTIFICATE_VERIFY_FAILED)

- **Issue**: "SSL: CERTIFICATE_VERIFY_FAILED: certificate verify failed: self-signed certificate in certificate chain"
- **Root cause**: Corporate proxy (Zscaler, Cisco, etc.) intercepts HTTPS with self-signed certificates
- **Solution for corporate networks**:
  1. Get root CA certificate from IT (usually a .crt or .pem file)
  2. Append to certifi bundle:
     ```bash
     cat /path/to/corporate-ca.crt >> $(python -m certifi)
     ```
  3. Or set environment variable:
     ```bash
     export REQUESTS_CA_BUNDLE="/path/to/corporate-ca.crt"
     ```
- **For non-corporate networks**: Update certifi with `uv pip install --upgrade certifi`

## Workflow Execution Issues

### "Manubot not available"

- Install Manubot: `uv pip install manubot` or `uv pip install -e ".[manubot-full]"`
- Citation resolution features will be disabled if not installed

### "Pandoc not found"

- Install Pandoc on your system (see Quick Start Step 1)
- PDF/DOCX/HTML generation requires Pandoc
- System-level installation required (not a Python package)

## Export and Formatting Issues

### "Citation resolution failed"

- Verify identifier format (DOI, PMID, etc.)
- Check internet connection
- Try manual resolution: `python main.py --resolve-citation doi:10.1038/...`
- Some identifiers may require network access

### "Submission package incomplete"

- Check `submission_checklist.md` for missing items
- Verify all workflow phases completed successfully
- Ensure figures and supplementary materials exist
- Run validation: `python main.py --validate-submission --journal ieee`

### "CSL style not found"

- Styles are downloaded automatically on first use
- Check internet connection
- Manually download from https://github.com/citation-style-language/styles
- Place in `data/cache/csl_styles/`
