from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


def test_env_example_documents_searxng_actions_variables_fallback() -> None:
    env_example = (ROOT_DIR / ".env.example").read_text(encoding="utf-8")

    start = env_example.index("# SearXNG 实例地址")
    end = env_example.index("SEARXNG_PUBLIC_INSTANCES_ENABLED=true", start)
    searxng_block = env_example[start:end]

    assert "GitHub Actions" in searxng_block
    assert "Variables" in searxng_block
    assert "Secrets" in searxng_block
    assert "vars.SEARXNG_BASE_URLS || secrets.SEARXNG_BASE_URLS" in searxng_block


def test_changelog_mentions_searxng_actions_variables_fallback() -> None:
    changelog = (ROOT_DIR / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")

    assert (
        "- [文档] 补充 SearXNG 自建实例地址在 GitHub Actions 中可按 "
        "Variables 优先、Secrets 回退方式透传的配置说明。"
    ) in changelog
