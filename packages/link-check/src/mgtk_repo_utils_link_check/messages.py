# SPDX-License-Identifier: Apache-2.0
"""Messages of the links tool(s): message id -> (English, Japanese)."""

MESSAGES: dict[str, tuple[str, str]] = {
    "summary-links": (
        "{links} link(s) checked in {files} file(s)",
        "{files} ファイルのリンク {links} 件を確認",
    ),
    "link-missing": (
        "link target `{target}` is not among the listed files; fix the path, or add the "
        "file to the index (a link to an untracked file breaks in other clones)",
        "リンク先 `{target}` が対象ファイルの一覧にない．パスを直すか，ファイルをインデックスに"
        "加える（追跡されていないファイルへのリンクは他の clone で壊れる）",
    ),
    "link-outside": (
        "link target `{target}` leaves the repository; use a path inside it",
        "リンク先 `{target}` がリポジトリの外を指す．リポジトリ内のパスにする",
    ),
    "link-anchor-missing": (
        "no heading or `<a id>` for `#{fragment}` in `{file}`; fix the fragment, or add the "
        "heading or anchor",
        "`{file}` に `#{fragment}` に当たる見出しも `<a id>` もない．"
        "フラグメントを直すか，見出しかアンカーを追加する",
    ),
}
