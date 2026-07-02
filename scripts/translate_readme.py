"""README 自动翻译脚本

将 README.md (中文) 翻译为 README.en.md (英文), 保留所有 Markdown 语法、
代码块、链接、图片引用和表格格式。

支持 OpenAI 兼容 API (OpenAI / DeepSeek / 智谱 / LM Studio 等)。

用法:
    # 本地执行
    python scripts/translate_readme.py

    # CI 环境 (GitHub Action)
    # 通过环境变量配置 API key 和 base_url

环境变量:
    OPENAI_API_KEY: API 密钥 (必需)
    OPENAI_BASE_URL: API 端点 (可选, 默认 https://api.openai.com/v1)
    OPENAI_MODEL: 模型名 (可选, 默认 gpt-4o-mini)
    TRANSLATE_SOURCE: 源文件 (可选, 默认 README.md)
    TRANSLATE_TARGET: 目标文件 (可选, 默认 README.en.md)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


SYSTEM_PROMPT = """You are a professional translator specializing in quantitative finance, software engineering, and academic research. Translate the following Chinese Markdown README to English.

Rules:
1. Preserve ALL Markdown syntax exactly: headers, lists, tables, code blocks, links, images, blockquotes.
2. Do NOT translate: code blocks content, variable names, function names, file paths, URLs, version numbers, package names.
3. Maintain technical accuracy: use standard quantitative finance terminology (e.g., "factor" not "agent", "orthogonalization" not "orthogonalisation" unless British English requested, "backtest" not "retrospective test").
4. Preserve all ADR references (ADR-XXX), section anchors (O1.12, O6.7), and cross-references.
5. Translate Chinese prose to natural, professional English. Avoid literal translation.
6. Keep the language switcher at the top: change "[English](README.en.md) | [中文](README.md)" to "[English](README.en.md) | [中文](README.md)" (no change needed, it's symmetric).
7. Do NOT add translator notes or comments. Output ONLY the translated Markdown.
8. If a section is already in English, keep it as-is.
9. Translate table headers but keep table structure intact.
10. Preserve emoji if any (the project generally avoids emoji per style guide)."""


def translate(content: str) -> str:
    """调用 LLM API 翻译内容"""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    try:
        from openai import OpenAI
    except ImportError:
        print("ERROR: openai package not installed. Run: pip install openai", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(api_key=api_key, base_url=base_url)

    print(f"Translating with model={model}, base_url={base_url}", file=sys.stderr)
    print(f"Source length: {len(content)} chars", file=sys.stderr)

    # 分块处理 (如果内容超过模型上下文)
    MAX_CHARS = 12000  # 保守上限, 留余量给 system prompt
    if len(content) <= MAX_CHARS:
        chunks = [content]
    else:
        # 按 ## 标题分块
        sections = content.split("\n## ")
        chunks = []
        current = sections[0]
        for section in sections[1:]:
            if len(current) + len(section) + 4 > MAX_CHARS:
                chunks.append(current)
                current = "## " + section
            else:
                current += "\n## " + section
        if current:
            chunks.append(current)

    print(f"Split into {len(chunks)} chunk(s)", file=sys.stderr)

    translated_parts = []
    for i, chunk in enumerate(chunks):
        print(f"Translating chunk {i+1}/{len(chunks)} ({len(chunk)} chars)...", file=sys.stderr)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": chunk},
            ],
            temperature=0.3,
        )
        translated_parts.append(response.choices[0].message.content)

    return "\n".join(translated_parts)


def main():
    source = Path(os.environ.get("TRANSLATE_SOURCE", "README.md"))
    target = Path(os.environ.get("TRANSLATE_TARGET", "README.en.md"))

    if not source.exists():
        print(f"ERROR: {source} not found", file=sys.stderr)
        sys.exit(1)

    content = source.read_text(encoding="utf-8")

    # 检查是否需要翻译 (跳过已英文的内容)
    if target.exists():
        existing = target.read_text(encoding="utf-8")
        if existing == content:
            print(f"SKIP: {target} already up-to-date", file=sys.stderr)
            return

    translated = translate(content)

    # 确保顶部有语言切换链接
    if "[English](README.en.md)" not in translated and "[中文](README.md)" not in translated:
        translated = "[English](README.en.md) | [中文](README.md)\n\n" + translated

    target.write_text(translated, encoding="utf-8")
    print(f"OK: translated {source} -> {target} ({len(translated)} chars)", file=sys.stderr)


if __name__ == "__main__":
    main()
