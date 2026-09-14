#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 GitHub 概览卡片 assets/stats.svg。

设计取舍：
  * 只读公开数据，纯标准库，Actions 上零依赖；
  * 生成的是仓库里的静态 SVG，不依赖 github-readme-stats 这类第三方实例
    （它的公共实例经常 503，README 里就会显示成裂图）；
  * 卡片里带「更新时间」，所以每周定时跑一定会产生一次真实提交。
"""

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://api.github.com"
UA = "profile-stats/1.0"
TZ_CN = timezone(timedelta(hours=8))
USER = os.environ.get("GH_USER", "birdger")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
OUT = os.environ.get("OUT_FILE", "assets/stats.svg")


def api(path):
    headers = {"User-Agent": UA, "Accept": "application/vnd.github+json"}
    if TOKEN:
        headers["Authorization"] = "Bearer " + TOKEN
    req = urllib.request.Request(API + path, headers=headers)
    with urllib.request.urlopen(req, timeout=45) as resp:
        body = resp.read().decode("utf-8", "replace")
        return json.loads(body) if body else None, dict(resp.headers)


def count_commits(full_name, fallback=0):
    """用 per_page=1 配合 Link 头里 last 页号，拿到该仓库的总提交数。"""
    try:
        _, headers = api("/repos/%s/commits?per_page=1" % full_name)
        link = headers.get("Link") or headers.get("link") or ""
        match = re.search(r'[?&]page=(\d+)>;\s*rel="last"', link)
        return int(match.group(1)) if match else 1
    except Exception:  # noqa: BLE001
        return fallback


def collect():
    user, _ = api("/users/" + USER)
    repos, _ = api("/users/%s/repos?per_page=100&sort=pushed" % USER)
    repos = repos or []

    stars = sum(r.get("stargazers_count", 0) or 0 for r in repos)
    forks = sum(r.get("forks_count", 0) or 0 for r in repos)
    languages = {}
    for r in repos:
        lang = r.get("language")
        if lang:
            languages[lang] = languages.get(lang, 0) + 1
    top_langs = [k for k, _ in sorted(languages.items(), key=lambda kv: -kv[1])[:4]]

    commits = 0
    for r in repos[:8]:
        if r.get("fork"):
            continue
        commits += count_commits(r["full_name"])

    last_push = ""
    for r in repos:
        if r.get("fork"):
            continue
        last_push = str(r.get("pushed_at") or "")[:10]
        break

    return {
        "login": user.get("login", USER),
        "repos": user.get("public_repos", len(repos)),
        "followers": user.get("followers", 0),
        "stars": stars,
        "forks": forks,
        "commits": commits,
        "langs": " · ".join(top_langs) if top_langs else "—",
        "last_push": last_push or "—",
        "updated": datetime.now(TZ_CN).strftime("%Y-%m-%d %H:%M"),
    }


def esc(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render(d):
    W, H = 495, 210
    bg, border, fg, dim, accent = "#1a1b27", "#2f334d", "#c8d3f5", "#828bb8", "#82aaff"
    items = [
        ("公开仓库", d["repos"]),
        ("获得 Star", d["stars"]),
        ("Followers", d["followers"]),
        ("提交总数", d["commits"]),
        ("主要语言", d["langs"]),
        ("最近推送", d["last_push"]),
    ]
    p = []
    p.append(
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" '
        'role="img" aria-label="%s 的 GitHub 概览">' % (W, H, W, H, esc(d["login"]))
    )
    p.append(
        '<rect x="0.5" y="0.5" width="%d" height="%d" rx="10" fill="%s" stroke="%s"/>'
        % (W - 1, H - 1, bg, border)
    )
    font = 'font-family="ui-sans-serif,-apple-system,Segoe UI,Noto Sans CJK SC,sans-serif"'
    p.append(
        '<text x="25" y="41" fill="%s" font-size="17" font-weight="600" %s>%s · GitHub 概览</text>'
        % (fg, font, esc(d["login"]))
    )
    p.append('<line x1="25" y1="55" x2="%d" y2="55" stroke="%s" stroke-width="1"/>' % (W - 25, border))

    for i, (label, value) in enumerate(items):
        col, row = i % 2, i // 2
        x = 25 + col * 232
        y = 88 + row * 38
        p.append('<text x="%d" y="%d" fill="%s" font-size="11.5" %s>%s</text>' % (x, y, dim, font, esc(label)))
        p.append(
            '<text x="%d" y="%d" fill="%s" font-size="15" font-weight="600" %s>%s</text>'
            % (x, y + 18, accent, font, esc(value))
        )

    p.append(
        '<text x="25" y="%d" fill="%s" font-size="10.5" %s>数据更新于 %s (UTC+8) · 本卡片由 GitHub Actions 自动生成</text>'
        % (H - 14, dim, font, esc(d["updated"]))
    )
    p.append("</svg>")
    return "\n".join(p)


def main():
    data = collect()
    svg = render(data)
    path = OUT
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg + "\n")
    print("[stats] 已写出 %s | 仓库 %s / star %s / 提交 %s / 语言 %s"
          % (path, data["repos"], data["stars"], data["commits"], data["langs"]))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print("[stats] 失败: %s" % exc, file=sys.stderr)
        sys.exit(1)
