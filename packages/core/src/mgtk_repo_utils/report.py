# SPDX-License-Identifier: Apache-2.0
"""Problem collection, report rendering and the message catalogue (en, ja)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

LANGS = ("en", "ja")

ERROR = "error"
WARNING = "warning"

# message id -> (English, Japanese). Every message for a rejected input names
# its remedy. Placeholders are filled with str.format.
MESSAGES: dict[str, tuple[str, str]] = {
    # report framing
    "header-problems": ("{tool}: {count} problem(s)", "{tool}: 問題 {count} 件"),
    "header-warnings": ("{tool}: {count} warning(s)", "{tool}: 警告 {count} 件"),
    "ok": ("{tool}: ok", "{tool}: ok"),
    "ok-summary": ("{tool}: ok ({summary})", "{tool}: ok（{summary}）"),
    # configuration and usage (standard error)
    "cfg-missing": (
        "configuration file not found: {path}; create it with `schema = 1` or pass --config",
        "設定ファイルが見つからない: {path}．`schema = 1` を含むファイルを作るか --config で指定する",
    ),
    "cfg-parse": (
        "{path}: invalid TOML ({detail}); fix the syntax",
        "{path}: TOML として不正（{detail}）．構文を直す",
    ),
    "cfg-schema-missing": (
        "{path}: `schema` is required; add `schema = 1`",
        "{path}: `schema` は必須．`schema = 1` を追加する",
    ),
    "cfg-schema-unsupported": (
        "{path}: `schema = {value}` is not supported by this release (mgtk-repo-utils {version} "
        "reads schema 1); use a release that supports it or change the file",
        "{path}: `schema = {value}` はこのリリース（mgtk-repo-utils {version}，schema 1 に対応）"
        "では扱えない．対応するリリースを使うか設定を直す",
    ),
    "cfg-requires-invalid": (
        "`requires` must look like \"0.1\" or \"0.1.2\", got {value}; write a version number",
        "`requires` は \"0.1\" か \"0.1.2\" の形式．{value} は不正なのでバージョン番号を書く",
    ),
    "cfg-requires-too-new": (
        "{path} requires mgtk-repo-utils {required} or later, but this release is {version}; "
        "install a newer release (hooks: move `rev`; a machine: reinstall the tool)",
        "{path} は mgtk-repo-utils {required} 以降を要求するが，このリリースは {version}．"
        "新しいリリースを入れる（hook は `rev` を進める．機械側はツールを入れ直す）",
    ),
    "cfg-unknown-key": (
        "unknown key `{name}` (this release is mgtk-repo-utils {version}); fix the typo, or "
        "use a newer release if the key comes from one",
        "未知のキー `{name}`（このリリースは mgtk-repo-utils {version}）．綴りを直すか，"
        "新しいリリースのキーなら新しいリリースを使う",
    ),
    "cfg-unknown-table": (
        "unknown table `[{name}]` (this release is mgtk-repo-utils {version}); fix the typo, "
        "use a newer release if the table comes from one, or install the tool that reads it "
        "(`mgtk-repo-utils tools` lists the installed ones)",
        "未知のテーブル `[{name}]`（このリリースは mgtk-repo-utils {version}）．綴りを直すか，"
        "新しいリリースのテーブルなら新しいリリースを使うか，その表を読むツールを入れる"
        "（`mgtk-repo-utils tools` が入っているものを一覧する）",
    ),
    "cfg-type": ("`{name}` must be {expected}", "`{name}` は{expected}でなければならない"),
    "type-string": ("a string", "文字列"),
    "type-boolean": ("a boolean", "真偽値"),
    "type-strings": ("an array of strings", "文字列の配列"),
    "type-table": ("a table", "テーブル"),
    "type-integer": ("an integer", "整数"),
    "cfg-enum": (
        "`{name}` must be one of {choices}, got {value}",
        "`{name}` は {choices} のいずれか．{value} は不正",
    ),
    "cfg-regex": (
        "`{name}` is not a valid regular expression ({detail}); fix the pattern",
        "`{name}` は正規表現として不正（{detail}）．パターンを直す",
    ),
    "cfg-required": ("`{name}` is required; add it", "`{name}` は必須．追加する"),
    "tool-disabled": (
        "[{table}] is absent in {path}, so {tool} is disabled; add the table or choose "
        "another file with --config",
        "{path} に [{table}] がないため {tool} は無効．テーブルを追加するか --config で別のファイルを指定する",
    ),
    "tool-duplicate": (
        "two installed distributions provide the tool {name!r} ({first}, {second}); "
        "uninstall one",
        "ツール {name!r} を 2 つの配布物（{first}，{second}）が提供している．どちらかを"
        "アンインストールすること",
    ),
    "root-missing": (
        "root is not a directory: {path}; pass an existing directory with --root",
        "ルートがディレクトリではない: {path}．存在するディレクトリを --root で指定する",
    ),
    "type-tables": ("an array of tables", "テーブルの配列"),
    # resolve
    # clone
    # frontmatter reader rules (key: fm-<rule>)
    "fm-missing": (
        "no frontmatter block; start the file with a line `---`",
        "frontmatter がない．ファイルの先頭を `---` の行にする",
    ),
    "fm-unterminated": (
        "frontmatter is not closed; add a closing line `---`",
        "frontmatter が閉じていない．閉じる `---` の行を追加する",
    ),
    "fm-plain-hash": (
        "unquoted value of `{key}` contains ` #`, which YAML reads as a comment and "
        "silently truncates; quote the value",
        "`{key}` の引用符なしの値に ` #` がある．YAML はここから先をコメントとして黙って切り捨てる．"
        "値を引用符で囲む",
    ),
    "fm-plain-hash-unread": (
        "unquoted value of `{key}` contains ` #`, which YAML reads as a comment and "
        "truncates (the key is not read by the configured tools); quote the value",
        "`{key}` の引用符なしの値に ` #` がある．YAML はここから先を切り捨てる"
        "（このキーは設定されたツールが読まない）．値を引用符で囲む",
    ),
    "fm-plain-colon": (
        "unquoted value of `{key}` contains `: ` or ends in `:`, which YAML reads as a "
        "mapping; quote the value",
        "`{key}` の引用符なしの値に `: ` があるか `:` で終わる．YAML はマッピングと読む．"
        "値を引用符で囲む",
    ),
    "fm-plain-colon-unread": (
        "unquoted value of `{key}` contains `: ` or ends in `:`, which YAML reads as a "
        "mapping (the key is not read by the configured tools); quote the value",
        "`{key}` の引用符なしの値に `: ` があるか `:` で終わる．YAML はマッピングと読む"
        "（このキーは設定されたツールが読まない）．値を引用符で囲む",
    ),
    "fm-plain-indicator": (
        "unquoted value of `{key}` starts with a YAML indicator (` @ %); quote the value",
        "`{key}` の引用符なしの値が YAML の予約文字（` @ %）で始まる．値を引用符で囲む",
    ),
    "fm-anchor": (
        "anchors (`&`) are not supported in `{key}`; write the value out or quote it",
        "`{key}` のアンカー（`&`）は扱えない．値を直接書くか引用符で囲む",
    ),
    "fm-alias": (
        "aliases (`*`) are not supported in `{key}`; write the value out or quote it",
        "`{key}` のエイリアス（`*`）は扱えない．値を直接書くか引用符で囲む",
    ),
    "fm-tag": (
        "tags (`!`) are not supported in `{key}`; remove the tag or quote the value",
        "`{key}` のタグ（`!`）は扱えない．タグを除くか値を引用符で囲む",
    ),
    "fm-quote-trailing": (
        "text follows the closing quote of `{key}`; remove it, or separate a comment "
        "with a space",
        "`{key}` の閉じ引用符の後ろに文字がある．取り除くか，コメントならスペースで区切る",
    ),
    "fm-tab-indent": (
        "tab in indentation; indent with spaces",
        "インデントにタブがある．スペースでインデントする",
    ),
    "fm-tab-before-comment": (
        "tab before a comment; separate the comment with spaces",
        "コメントの前にタブがある．スペースで区切る",
    ),
    "fm-duplicate-key": (
        "duplicate key `{key}`; keep one",
        "キー `{key}` が重複している．1 つにする",
    ),
    "fm-nested-flow": (
        "nested flow collections are not supported in `{key}`; use a flat list of scalars",
        "`{key}` の入れ子のフロー形式は扱えない．スカラーのみの平らなリストにする",
    ),
    "fm-flow-mapping": (
        "flow mappings (`{{`) are not supported in `{key}`; write a scalar or quote the value",
        "`{key}` のフローマッピング（`{{`）は扱えない．スカラーにするか値を引用符で囲む",
    ),
    "fm-list-item-not-indented": (
        "a list item at the key's own indentation; indent the `- ` lines under the key",
        "リスト項目がキーと同じインデントにある．`- ` の行をキーより深くインデントする",
    ),
    "fm-bad-date": (
        "`{key}` is not a valid date; write YYYY-MM-DD",
        "`{key}` が正しい日付ではない．YYYY-MM-DD で書く",
    ),
    "fm-list-expected": (
        "`{key}` must be a list; write `[a, b]` or `- item` lines",
        "`{key}` はリストでなければならない．`[a, b]` か `- 項目` の行で書く",
    ),
    "fm-scalar-expected": (
        "`{key}` must be a single value, not a list; write one value",
        "`{key}` は単一の値でなければならない．リストではなく 1 つの値にする",
    ),
    "fm-unterminated-quote": (
        "the quoted value of `{key}` is not closed; add the closing quote",
        "`{key}` の引用符が閉じていない．閉じ引用符を追加する",
    ),
    "fm-bad-escape": (
        "unsupported escape in the double-quoted value of `{key}` (use \\\", \\\\, \\n, \\t); "
        "remove it or use single quotes",
        "`{key}` の二重引用符の値に未対応のエスケープがある（使えるのは \\\"，\\\\，\\n，\\t）．"
        "除くか一重引用符にする",
    ),
    "fm-flow-unterminated": (
        "the flow list of `{key}` is not closed on its line; write it on one line, or use "
        "`- item` lines",
        "`{key}` のフローリストが同じ行で閉じていない．1 行で書くか `- 項目` の行にする",
    ),
    "fm-flow-trailing": (
        "text follows the closing `]` of `{key}`; remove it, or separate a comment with a space",
        "`{key}` の `]` の後ろに文字がある．取り除くか，コメントならスペースで区切る",
    ),
    "fm-flow-empty-item": (
        "empty item in the flow list of `{key}`; remove the extra comma",
        "`{key}` のフローリストに空の項目がある．余分なカンマを除く",
    ),
    "fm-block-scalar-indicator": (
        "unsupported block scalar header for `{key}` (only |, |-, > and >-); remove the "
        "indentation or keep indicator",
        "`{key}` のブロックスカラーの指定が未対応（使えるのは |，|-，>，>- のみ）．"
        "インデント指示子や + を除く",
    ),
    "fm-syntax": (
        "line is not `key: value` or a continuation of the previous key; fix or remove it",
        "`key: value` でも直前のキーの続きでもない行．直すか削除する",
    ),
    # issues-view
    "tracked-missing": (
        "listed in the index but missing from the working tree; skipped (restore the "
        "file or run `git rm`)",
        "インデックスにあるが作業ツリーにない．読み飛ばした（復元するか `git rm` する）",
    ),
    "file-unreadable": (
        "cannot read the file as UTF-8 ({detail}); save it as UTF-8",
        "UTF-8 として読めない（{detail}）．UTF-8 で保存し直す",
    ),
    # freeze-lint
    # link-check
    # view body wording
}


def register(messages: Mapping[str, tuple[str, str]]) -> None:
    """Add a tool's messages to the catalogue (called at discovery, design section 3)."""
    MESSAGES.update(messages)


def message(lang: str, msg_id: str, **params: object) -> str:
    english, japanese = MESSAGES[msg_id]
    return (japanese if lang == "ja" else english).format(**params)


def severity_for(setting: str) -> str:
    """Map a configured severity ("warn" | "error") to a problem severity."""
    return WARNING if setting == "warn" else ERROR


class ToolError(Exception):
    """A usage or configuration error: printed to standard error, exit code 2."""


@dataclass(frozen=True)
class Problem:
    path: str
    line: int | None
    severity: str
    msg_id: str
    text: str

    def render(self) -> str:
        where = self.path if self.line is None else f"{self.path}:{self.line}"
        return f"{where}: {self.text}"


@dataclass
class Report:
    tool: str
    lang: str
    items: list[Problem] = field(default_factory=list)

    def add(
        self, severity: str, msg_id: str, path: str, line: int | None = None, **params: object
    ) -> None:
        text = message(self.lang, msg_id, **params)
        self.items.append(Problem(path, line, severity, msg_id, text))

    def error(self, msg_id: str, path: str, line: int | None = None, **params: object) -> None:
        self.add(ERROR, msg_id, path, line, **params)

    def warn(self, msg_id: str, path: str, line: int | None = None, **params: object) -> None:
        self.add(WARNING, msg_id, path, line, **params)

    @property
    def problems(self) -> list[Problem]:
        return [p for p in self.items if p.severity == ERROR]

    @property
    def warnings(self) -> list[Problem]:
        return [p for p in self.items if p.severity == WARNING]

    @property
    def exit_code(self) -> int:
        return 1 if self.problems else 0

    def lines(self, summary: str = "") -> list[str]:
        """Render the report: problems, then warnings, then `ok` when there is no problem."""
        out: list[str] = []
        for header, group in (
            ("header-problems", self.problems),
            ("header-warnings", self.warnings),
        ):
            if group:
                out.append(message(self.lang, header, tool=self.tool, count=len(group)))
                ordered = sorted(group, key=lambda p: (p.path, p.line or 0, p.text))
                out.extend(p.render() for p in ordered)
        if not self.problems:
            if summary:
                out.append(message(self.lang, "ok-summary", tool=self.tool, summary=summary))
            else:
                out.append(message(self.lang, "ok", tool=self.tool))
        return out
