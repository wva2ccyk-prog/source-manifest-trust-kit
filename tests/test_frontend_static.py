from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


def test_frontend_loads_dompurify_before_app() -> None:
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")

    purify_pos = html.index('src="purify.min.js"')
    app_pos = html.index('src="app.js"')

    assert purify_pos < app_pos


def test_operator_package_markdown_requires_sanitizer_or_escaped_fallback() -> None:
    app_js = (FRONTEND / "app.js").read_text(encoding="utf-8")

    assert "typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined'" in app_js
    assert "DOMPurify.sanitize(html)" in app_js
    assert "escapeHTML(markdownText)" in app_js


def test_frontend_uses_backend_source_type_values() -> None:
    app_js = (FRONTEND / "app.js").read_text(encoding="utf-8")

    for source_type in [
        "official",
        "company",
        "news",
        "analyst",
        "community",
        "social",
        "user_note",
        "unknown",
    ]:
        assert f'value="{source_type}"' in app_js


def test_frontend_includes_operator_ux_polish_controls() -> None:
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    app_js = (FRONTEND / "app.js").read_text(encoding="utf-8")

    for element_id in [
        "btn-select-all",
        "btn-clear-all",
        "file-import-selection",
        "artifact-state-panel",
        "workflow-checklist",
        "package-summary-header",
        "package-jump-list",
    ]:
        assert element_id in html

    for behavior_hook in [
        "function getSuggestions",
        "fileImportSelection",
        "selected_candidates",
        "filter-chip",
        "renderPackageSummaryHeader",
        "collapsibleHeaders",
    ]:
        assert behavior_hook in app_js


def test_frontend_states_public_static_viewer_boundary() -> None:
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")

    for phrase in [
        "Static Preview Boundary",
        "previews local artifacts only",
        "not API-backed",
        "not a CLI orchestrator",
        "production app",
        "truth adjudicator",
        "finance-advice surface",
    ]:
        assert phrase in html


def test_frontend_session_restore_does_not_persist_file_contents() -> None:
    app_js = (FRONTEND / "app.js").read_text(encoding="utf-8")

    assert "localStorage.setItem('trust_os_session'" in app_js
    assert "File contents are not persisted for safety" in app_js
    assert "readAsText(file)" in app_js
    assert "file_contents" not in app_js
    assert "markdownText" not in app_js[app_js.index("function saveSession") : app_js.index("function restoreSession")]


def test_frontend_filters_non_http_urls_before_anchor_creation() -> None:
    app_js = (FRONTEND / "app.js").read_text(encoding="utf-8")

    assert "function safeHttpUrl" in app_js
    assert "url.protocol === 'http:' || url.protocol === 'https:'" in app_js
    assert "urlA.href = safeCandidateUrl" in app_js
    assert "aUrl.href = safeUrl" in app_js
    assert "urlA.href = cand.url" not in app_js
    assert "aUrl.href = url" not in app_js
