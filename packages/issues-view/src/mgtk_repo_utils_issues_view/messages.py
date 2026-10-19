# SPDX-License-Identifier: Apache-2.0
"""Messages of the issues tool(s): message id -> (English, Japanese)."""

MESSAGES: dict[str, tuple[str, str]] = {
    "summary-issues": (
        "{items} item(s): {active} active, {deferred} deferred, {terminal} done; "
        "{views} view(s) checked",
        "{items} 件（active {active}，deferred {deferred}，終了 {terminal}）；"
        "ビュー {views} 件を確認",
    ),
    "summary-wrote": ("wrote {written} view(s)", "ビュー {written} 件を更新"),
    "layout-stray": (
        "`{name}` is not allowed in the issues directory (allowed: README.md, the template, "
        "registered view files and the items); move or remove it",
        "`{name}` は issues ディレクトリに置けない（置けるのは README.md，テンプレート，"
        "登録したビューのファイル，items のみ）．移動するか削除する",
    ),
    "layout-item-name": (
        "`{name}` is not an item: the file stem must fully match id_pattern `{pattern}` "
        "and the name end in .md; rename it, or list it in items_allow",
        "`{name}` は item ではない．ファイル名の stem が id_pattern `{pattern}` に完全一致し "
        "拡張子が .md である必要がある．名前を直すか items_allow に載せる",
    ),
    "layout-subdir": (
        "subdirectories are not allowed among the items; move the file up or remove it",
        "items の中にサブディレクトリは置けない．ファイルを上に移すか削除する",
    ),
    "id-missing": (
        "`id` is required; add `id: {stem}`",
        "`id` は必須．`id: {stem}` を追加する",
    ),
    "id-mismatch": (
        "`id` is `{value}` but the file name is `{stem}`; make them equal",
        "`id` が `{value}` だがファイル名は `{stem}`．同じにする",
    ),
    "title-missing": (
        "no title; add a `title` field",
        "タイトルがない．`title` を追加する",
    ),
    "title-missing-h1": (
        "no title; add a `title` field or a `# ` heading after the frontmatter",
        "タイトルがない．`title` か frontmatter の後ろの `# ` 見出しを追加する",
    ),
    "created-missing": (
        "`created` is required; add `created: YYYY-MM-DD`",
        "`created` は必須．`created: YYYY-MM-DD` を追加する",
    ),
    "status-missing": (
        "`status` is required; use one of {choices}",
        "`status` は必須．{choices} のいずれかにする",
    ),
    "status-unknown": (
        "status `{value}` is not in [issues.status] (known: {choices}); use a known "
        "status or add it to the configuration",
        "status `{value}` は [issues.status] にない（既知: {choices}）．既知の status にするか設定に追加する",
    ),
    "status-other": (
        "status `{value}` is not in [issues.status]; counted as `other`",
        "status `{value}` は [issues.status] にない．`other` として数える",
    ),
    "field-missing": (
        "`{key}` is required (one of {choices}); add it",
        "`{key}` は必須（{choices} のいずれか）．追加する",
    ),
    "field-unknown": (
        "`{key}` is `{value}`, not one of {choices}; use a listed value",
        "`{key}` が `{value}` で，{choices} にない．リストにある値にする",
    ),
    "terminal-field-missing": (
        "`{key}` must be non-empty when the status is `{status}`; fill it in",
        "status が `{status}` のとき `{key}` は空にできない．値を入れる",
    ),
    "closed-on-open": (
        "`closed` is set but the status `{status}` is not terminal; clear `closed` or "
        "change the status",
        "`closed` があるが status `{status}` は終了ではない．`closed` を消すか status を直す",
    ),
    "view-missing": (
        "view file does not exist; create it with the marker lines for `{marker}`",
        "ビューのファイルがない．`{marker}` のマーカー行を含むファイルを作る",
    ),
    "marker-begin-missing": (
        "no line `<!-- BEGIN GENERATED: {marker} -->`; add the marker lines, each alone on its line",
        "`<!-- BEGIN GENERATED: {marker} -->` の行がない．マーカー行を 1 行ずつ単独で追加する",
    ),
    "marker-begin-multiple": (
        "{count} BEGIN lines for `{marker}` (lines {lines}); keep exactly one",
        "`{marker}` の BEGIN 行が {count} 個ある（{lines} 行目）．1 つだけにする",
    ),
    "marker-end-missing": (
        "no line `<!-- END GENERATED: {marker} -->` after the BEGIN line; add it",
        "BEGIN 行の後ろに `<!-- END GENERATED: {marker} -->` の行がない．追加する",
    ),
    "marker-end-multiple": (
        "{count} END lines for `{marker}` after the BEGIN line (lines {lines}); keep exactly one",
        "BEGIN 行の後ろに `{marker}` の END 行が {count} 個ある（{lines} 行目）．1 つだけにする",
    ),
    "marker-end-before-begin": (
        "END line for `{marker}` precedes the BEGIN line; remove it or move it below the BEGIN line",
        "`{marker}` の END 行が BEGIN 行より前にある．除くか BEGIN 行の後ろに移す",
    ),
    "view-stale": (
        "generated region `{marker}` is out of date; run `mgtk-repo-utils issues-view --write`",
        "生成領域 `{marker}` が古い．`mgtk-repo-utils issues-view --write` を実行する",
    ),
    "untracked-row": (
        "view `{view}` lists `{id}`, which is not tracked; stage the item with the view, "
        "or the view breaks in other clones",
        "ビュー `{view}` が追跡されていない `{id}` を載せている．"
        "ビューと一緒に item をステージする（しないと他の clone でビューが壊れる）",
    ),
    "untracked-item": (
        'not tracked, so the views leave it out (`read = "tracked"`); stage it to include it',
        '追跡されていないのでビューに載らない（`read = "tracked"`）．載せるにはステージする',
    ),
    "count-active": ("active", "active"),
    "count-deferred": ("deferred", "deferred"),
    "count-terminal": ("done", "終了"),
    "label-title": ("title", "タイトル"),
    "none-group": ("(none)", "（なし）"),
    "cfg-marker": (
        "`{name}` must match [a-z0-9-]+, got {value}; use lowercase letters, digits and hyphens",
        "`{name}` は [a-z0-9-]+ に一致する必要がある．{value} は不正なので小文字，数字，ハイフンにする",
    ),
    "cfg-duplicate-status": (
        "status `{value}` is listed in more than one class of [issues.status]; list it once",
        "status `{value}` が [issues.status] の複数の区分に含まれる．1 か所だけに書く",
    ),
    "cfg-view-name": (
        "view file name `{value}` must be a plain file name inside the issues directory; "
        "remove the directory part",
        "ビューのファイル名 `{value}` は issues ディレクトリ直下のファイル名でなければならない．"
        "ディレクトリ部分を除く",
    ),
    "cfg-unknown-status": (
        "`{name}` names status `{value}`, which is not in [issues.status]; use a configured status",
        "`{name}` の status `{value}` は [issues.status] にない．設定済みの status を使う",
    ),
}
