# SPDX-License-Identifier: Apache-2.0
"""Messages of the clone tool(s): message id -> (English, Japanese)."""

MESSAGES: dict[str, tuple[str, str]] = {
    "resolve-yaml-missing": (
        "PyYAML is required to read the registries but is not installed in this environment; "
        "reinstall mgtk-repo-utils (PyYAML is one of its dependencies), or run "
        "`uvx --from \"git+<repository URL>@<commit>\" --with pyyaml mgtk-repo-utils {command}`",
        "レジストリの読み込みに PyYAML が必要だが，この環境にはインストールされていない．"
        "mgtk-repo-utils を入れ直す（PyYAML は依存の一つ）か，"
        "`uvx --from \"git+<repository URL>@<commit>\" --with pyyaml mgtk-repo-utils {command}` "
        "で実行する",
    ),
    "resolve-file-unreadable": (
        "{path}: cannot read the registry ({detail}); create the file, or fix `file` of {source}",
        "{path}: レジストリを読めない（{detail}）．ファイルを作るか，{source} の `file` を直す",
    ),
    "resolve-yaml-line": (
        "{path}: invalid YAML at line {line} ({detail}); fix the syntax",
        "{path}: YAML として不正（{line} 行目: {detail}）．構文を直す",
    ),
    "resolve-yaml-error": (
        "{path}: invalid YAML ({detail}); fix the syntax",
        "{path}: YAML として不正（{detail}）．構文を直す",
    ),
    "resolve-top-level": (
        "{path}: the top level must be a mapping, and an empty file is not one; write the "
        "registry as `key: value` pairs",
        "{path}: トップレベルはマッピングでなければならない（空のファイルも不可）．"
        "レジストリを `key: value` の形で書く",
    ),
    "expand-unset": (
        "`{variable}` is unset or empty, but root `{root}` (`{text}`) needs it; set it to an "
        "absolute path",
        "`{variable}` が未設定か空だが，root `{root}`（`{text}`）に必要．絶対パスを設定する",
    ),
    "expand-bad": (
        "`{variable}` is `{value}`, which is not an absolute path without control characters, "
        "but root `{root}` (`{text}`) needs one; set it to such a path",
        "`{variable}` が `{value}` で，制御文字のない絶対パスではないが，root `{root}`（`{text}`）には"
        "それが必要．そのようなパスを設定する",
    ),
    "kind-absent": ("absent", "キーがない"),
    "kind-null": ("null", "null"),
    "kind-empty": ("an empty string", "空文字列"),
    "kind-string": ("a string", "文字列"),
    "kind-mapping": ("a mapping", "マッピング"),
    "kind-list": ("a list", "リスト"),
    "kind-boolean": ("a boolean", "真偽値"),
    "kind-number": ("a number", "数値"),
    "kind-date": ("a date", "日付"),
    "kind-other": ("another type", "別の型"),
    "name-id": ("id", "id"),
    "name-alias": ("alias", "alias"),
    "name-url": ("URL", "URL"),
    "walk-list": (
        "`[]` after `{key}` needs a list, but the value is {kind}; fix the registry, or "
        "`entries` of {source}",
        "`{key}` に続く `[]` はリストを要求するが，値は{kind}．レジストリか {source} の `entries` を直す",
    ),
    "walk-key": (
        "the key `{key}` is looked up in {kind}, not a mapping; fix the registry, or "
        "`entries` of {source}",
        "キー `{key}` を{kind}の中で探している（マッピングではない）．"
        "レジストリか {source} の `entries` を直す",
    ),
    "walk-final": (
        "the value is {kind}, not a mapping, so it is not an entry; fix the registry, or "
        "`entries` of {source}",
        "値が{kind}でマッピングではなく，エントリにならない．レジストリか {source} の `entries` を直す",
    ),
    "source-empty": (
        "no entry in `{file}` at `entries = {entries}`; an empty result looks like a "
        "misspelt key, so fix `entries`, or remove the source until it has entries",
        "`{file}` の `entries = {entries}` にエントリがない．空の結果は綴り違いと区別できないので，"
        "`entries` を直すか，エントリができるまでソースを設定から外す",
    ),
    "entry-value": (
        "`{key}` must be a non-empty string, but it is {kind}; give it a non-empty string "
        "(quote a value YAML reads as a boolean, number or date)",
        "`{key}` は空でない文字列でなければならないが，{kind}．空でない文字列にする"
        "（YAML が真偽値，数値，日付と読む値は引用符で囲む）",
    ),
    "entry-no-id": (
        "the id cannot be determined: the URL gives no basename; set `id` to the key that "
        "holds the id, or fix the URL",
        "id を決められない: URL から basename が得られない．`id` に id を持つキーを指定するか，"
        "URL を直す",
    ),
    "entry-aliases": (
        "`{key}` must be a list of non-empty strings, but it is {kind}; write such a list, "
        "or remove the key",
        "`{key}` は空でない文字列のリストでなければならないが，{kind}．そのようなリストにするか，"
        "キーを除く",
    ),
    "entry-chars": (
        "{kind} `{value}` contains whitespace or a control character; remove it",
        "{kind} `{value}` に空白か制御文字がある．取り除く",
    ),
    "entry-dash": (
        "{kind} `{value}` begins with `-`, which a command line reads as an option; rename it",
        "{kind} `{value}` が `-` で始まる．コマンドラインではオプションと読まれるので名前を変える",
    ),
    "entry-dir": (
        "directory name `{value}` is not one path component (empty, `.` or `..`, holding `/`, "
        "`\\`, NUL or a control character, or beginning with `-`); change the id or the URL, "
        "or switch `dir` between \"id\" and \"url\"",
        "ディレクトリ名 `{value}` が 1 つのパス成分ではない（空，`.`，`..`，`/`，`\\`，NUL，制御文字を"
        "含む，または `-` で始まる）．id か URL を直すか，`dir` を \"id\" と \"url\" で切り替える",
    ),
    "alias-is-id": (
        "alias `{value}` equals the entry's own id; remove it from the aliases",
        "alias `{value}` がエントリ自身の id と同じ．alias から除く",
    ),
    "alias-repeated": (
        "alias `{value}` is listed more than once; keep one",
        "alias `{value}` が複数回書かれている．1 つにする",
    ),
    "id-collision": (
        "`{value}` is also an id or alias of {other}; rename one of them",
        "`{value}` は {other} の id か alias でもある．どちらかの名前を変える",
    ),
    "url-unmatched": (
        "URL `{value}` matches no pattern of `clone.urls`; fix the URL, or add a pattern "
        "for its host to `clone.urls`",
        "URL `{value}` が `clone.urls` のどのパターンにも一致しない．URL を直すか，"
        "そのホストのパターンを `clone.urls` に加える",
    ),
    "url-helper": (
        "URL `{value}` uses git's remote-helper syntax (`<transport>::<address>`), which "
        "clone does not support whatever `clone.urls` says; write a plain URL (a scheme URL, "
        "`host:path` or a path)",
        "URL `{value}` が git のリモートヘルパーの書式（`<transport>::<address>`）で，"
        "`clone.urls` の内容にかかわらず clone は扱わない．通常の URL（スキーム付き URL，"
        "`host:パス`，パス）で書く",
    ),
    "local-type": (
        "`{key}` must be a string, but it is {kind}; write the destination as `~/<path>`, "
        "`/<path>` or `$NAME/<path>`, or remove the key",
        "`{key}` は文字列でなければならないが，{kind}．`~/<パス>`，`/<パス>`，`$NAME/<パス>` の形で"
        "書くか，キーを除く",
    ),
    "local-form": (
        "declared deviation `{value}` must be `~/<path>`, `/<path>` or `$NAME/<path>`, with "
        "no empty, `.` or `..` component and no control character; fix the path",
        "宣言された例外 `{value}` は `~/<パス>`，`/<パス>`，`$NAME/<パス>` のいずれかで，"
        "空・`.`・`..` の成分と制御文字を持てない．パスを直す",
    ),
    "local-outside": (
        "declared deviation `{value}` lies outside every root (it must begin with a root's "
        "declared text and `/`, in that spelling); write it in a root's spelling, or exclude "
        "the entry instead",
        "宣言された例外 `{value}` がどの root の中にもない（root の宣言どおりの綴りと `/` で始まる必要がある）．"
        "root の綴りで書くか，代わりにエントリを除外する",
    ),
    "local-default": (
        "declared deviation `{value}` equals the default destination; delete the `{key}` value",
        "宣言された例外 `{value}` が既定の配置先と同じ．`{key}` の値を削除する",
    ),
    "dest-overlap": (
        "destination `{dest}` equals, contains or lies inside the destination `{other_dest}` "
        "of {other}; give one of them another directory name or a declared deviation, or "
        "exclude it",
        "配置先 `{dest}` が {other} の配置先 `{other_dest}` と同じか，含むか，含まれる．"
        "どちらかのディレクトリ名を変えるか例外を宣言するか，除外する",
    ),
    "dest-root": (
        "destination `{dest}` equals or contains root `{root}` (`{root_text}`); give the entry "
        "another directory name or a declared deviation, or exclude it",
        "配置先 `{dest}` が root `{root}`（`{root_text}`）と同じか，root を含む．"
        "エントリのディレクトリ名を変えるか例外を宣言するか，除外する",
    ),
    "exclude-unmatched": (
        "`exclude` lists `{value}`, which matches no id or alias of the source's entries; "
        "remove it, or fix the id",
        "`exclude` の `{value}` がソースのどのエントリの id にも alias にも一致しない．"
        "除くか id を直す",
    ),
    "clone-git-missing": (
        "git is not installed or not on PATH; install git or fix PATH",
        "git がインストールされていないか PATH にない．git をインストールするか PATH を直す",
    ),
    "clone-git-env": (
        "`git rev-parse --local-env-vars` failed ({detail}); use git 1.7.1 or later",
        "`git rev-parse --local-env-vars` が失敗した（{detail}）．git 1.7.1 以降を使う",
    ),
    "clone-git-unrunnable": (
        "git cannot be run ({detail}); fix its permissions or PATH",
        "git を実行できない（{detail}）．権限か PATH を直す",
    ),
    "clone-stat": (
        "cannot inspect {path} ({detail}); fix its permissions or the path",
        "{path} を調べられない（{detail}）．権限かパスを直す",
    ),
    "clone-root-missing": (
        "root `{root}` is not an existing directory: {path}; if that is the intended "
        "location, create it with `mkdir -p {quoted}`, otherwise fix the root's variable or path",
        "root `{root}` が存在するディレクトリではない: {path}．そこでよければ "
        "`mkdir -p {quoted}` で作る．違えば root の変数かパスを直す",
    ),
    "clone-parent-missing": (
        "the parent of the declared destination is not an existing directory: {path}; if that "
        "is the intended location, create it with `mkdir -p {quoted}`, otherwise fix the "
        "declaration",
        "宣言された配置先の親が存在するディレクトリではない: {path}．そこでよければ "
        "`mkdir -p {quoted}` で作る．違えば宣言を直す",
    ),
    "clone-escapes": (
        "{dest} resolves to {real}, which is not strictly inside root `{root}` ({real_root}); "
        "remove or fix the symlink, or fix the declaration",
        "{dest} は {real} に解決され，root `{root}`（{real_root}）の厳密に内側ではない．"
        "シンボリックリンクを除くか直すか，宣言を直す",
    ),
    "clone-other-root": (
        "{dest} resolves to {real}, which equals or contains root `{other}` ({real_other}); "
        "give the entry another directory name, or fix the root variables",
        "{dest} は {real} に解決され，root `{other}`（{real_other}）と同じか，それを含む．"
        "エントリのディレクトリ名を変えるか，root の変数を直す",
    ),
    "clone-gitdir-outside": (
        "{dest} keeps its repository data outside root `{root}` (git directory {gitdir}), as a "
        "linked worktree does, so the tool does not touch it; place a standalone clone there "
        "(move the checkout away, or remove the worktree with `git worktree remove`) and run "
        "the command again",
        "{dest} はリポジトリのデータを root `{root}` の外（git ディレクトリ {gitdir}）に持つ"
        "（リンクされたワークツリーなど）ので，ツールは触れない．単独のクローンを置く"
        "（チェックアウトを移動するか，`git worktree remove` でワークツリーを除く）"
        "してから，もう一度実行する",
    ),
    "clone-failed": (
        "`git clone` exited with {code} (git's message is above); fix the cause and run the "
        "command again",
        "`git clone` が終了コード {code} で終わった（git のメッセージは上）．原因を直して"
        "もう一度実行する",
    ),
    "clone-file": (
        "{dest} is a file, not a checkout; move it away, or give the entry another directory name",
        "{dest} はファイルでありチェックアウトではない．移動するか，エントリのディレクトリ名を変える",
    ),
    "clone-dangling": (
        "{dest} is a dangling symlink; remove it or repair its target, then run the command again",
        "{dest} は宛先のないシンボリックリンク．除くか宛先を直してから，もう一度実行する",
    ),
    "clone-empty": (
        "{dest} is an empty directory; remove it with `rmdir {quoted}` and run the command again",
        "{dest} は空のディレクトリ．`rmdir {quoted}` で除いてから，もう一度実行する",
    ),
    "clone-bare": (
        "{dest} is a bare repository, not a checkout; move it away, or give the entry another "
        "directory name",
        "{dest} はベアリポジトリでありチェックアウトではない．移動するか，エントリのディレクトリ名を変える",
    ),
    "clone-not-checkout": (
        "{dest} is not the top of a checkout ({detail}); move it away, or give the entry "
        "another directory name",
        "{dest} はチェックアウトの最上位ではない（{detail}）．移動するか，エントリのディレクトリ名を変える",
    ),
    "detail-inside-worktree": (
        "it lies inside another work tree", "別のワークツリーの内側にある"
    ),
    "detail-inside-git-dir": ("it lies inside a git directory", "git ディレクトリの内側にある"),
    "detail-git-exit": ("git exited with {code}", "git が終了コード {code} で終わった"),
    "clone-git-failed": (
        "`git {args}` failed in {dest} ({detail}); repair the checkout by hand",
        "{dest} で `git {args}` が失敗した（{detail}）．チェックアウトを手で直す",
    ),
    "clone-no-origin": (
        "{dest} has no `origin` URL, but the registry declares `{url}`; if it is the same "
        "repository, run `git -C {qdest} remote add origin {qurl}`",
        "{dest} に `origin` の URL がないが，レジストリは `{url}` を宣言している．同じリポジトリなら "
        "`git -C {qdest} remote add origin {qurl}` を実行する",
    ),
    "clone-origin-several": (
        "{dest} has several `origin` URLs (`{found}`), but the registry declares `{url}`; leave "
        "one with `git -C {qdest} config --replace-all remote.origin.url {qurl}` if it is the "
        "same repository",
        "{dest} の `origin` の URL が複数ある（`{found}`）が，レジストリは `{url}` を宣言している．"
        "同じリポジトリなら `git -C {qdest} config --replace-all remote.origin.url {qurl}` で"
        "1 つにする",
    ),
    "clone-origin-differs": (
        "{dest} has origin `{found}`, but the registry declares `{url}`; if the registry is right, "
        "run `git -C {qdest} remote set-url origin {qurl}`, otherwise fix the registry",
        "{dest} の origin は `{found}` だが，レジストリは `{url}` を宣言している．レジストリが正しければ "
        "`git -C {qdest} remote set-url origin {qurl}` を実行する．違えばレジストリを直す",
    ),
    "clone-pull-failed": (
        "`git pull --ff-only` exited with {code} in {dest} (git's message is above); bring the "
        "checkout up to date by hand",
        "{dest} で `git pull --ff-only` が終了コード {code} で終わった（git のメッセージは上）．"
        "チェックアウトを手で更新する",
    ),
    "resolve-unknown": (
        "no entry has the id or alias `{id}`; check the spelling against the registry "
        "(`resolve --check` reads every entry)",
        "id にも alias にも `{id}` を持つエントリがない．レジストリと綴りを照らし合わせる"
        "（`resolve --check` が全エントリを読む）",
    ),
    "resolve-excluded": (
        "`{id}` is excluded by `exclude` of {source}, so the tools do not handle it; remove "
        "it from `exclude` to handle it",
        "`{id}` は {source} の `exclude` で除外されており，ツールは扱わない．"
        "扱うなら `exclude` から外す",
    ),
    "summary-resolve": (
        "{entries} entr(ies) from {sources} source(s), {excluded} excluded",
        "{sources} 件のソースからエントリ {entries} 件，うち除外 {excluded} 件",
    ),
    "resolve-usage": (
        "give exactly one of an id and --check",
        "id と --check のどちらか一方だけを指定する",
    ),
    "summary-clone-cloned": ("cloned {id} to {dest}", "{id} を {dest} にクローンした"),
    "summary-clone-present": ("{id} is present at {dest}", "{id} は {dest} にある"),
    "summary-clone-updated": ("updated {id} at {dest}", "{id} を {dest} で更新した"),
    "cfg-clone-empty": (
        "`{name}` must not be empty; declare at least one",
        "`{name}` は空にできない．少なくとも 1 つ宣言する",
    ),
    "cfg-clone-root-name": (
        "root name {value} in `{name}` must match [A-Za-z0-9_-]+; rename it",
        "`{name}` の root の名前 {value} は [A-Za-z0-9_-]+ に一致する必要がある．名前を変える",
    ),
    "cfg-clone-root-form": (
        "`{name}` must be `~/<path>`, `/<path>` or `$NAME` alone, without empty, `.` or `..` "
        "components (no trailing `/`), got {value}; write the path in one of these forms",
        "`{name}` は `~/<パス>`，`/<パス>`，`$NAME` 単独のいずれかで，空・`.`・`..` の成分"
        "（末尾の `/` を含む）を持てない．{value} は不正なのでこの形で書く",
    ),
    "cfg-clone-url-pattern": (
        "pattern {value} in `{name}` must begin with a literal `<scheme>://<host>/`, "
        "`[<user>@]<host>:` or `/`, with no `*` or `?` before that point, and neither the "
        "pattern nor its host may begin with `-`; write the transport and the host out",
        "`{name}` のパターン {value} は，リテラルの `<scheme>://<host>/`，`[<user>@]<host>:`，"
        "`/` のいずれかで始まり，そこまでに `*` も `?` も含めてはならない．パターンもホストも "
        "`-` で始めてはならない．転送方式とホストを書き出す",
    ),
    "cfg-clone-file": (
        "`{name}` must be a path inside the repository, relative and without `..`, got "
        "{value}; give the registry's path from the repository root",
        "`{name}` はリポジトリ内のパス（相対パスで `..` なし）でなければならない．{value} は不正なので"
        "リポジトリのルートからのレジストリのパスを書く",
    ),
    "cfg-clone-entries": (
        "`{name}` must be keys joined by `.`, each optionally followed by `[]` "
        "(for example `teams[].services[]`), got {value}; write the path to the entries",
        "`{name}` は `.` でつないだキー（それぞれ `[]` を付けてよい．例 `teams[].services[]`）"
        "でなければならない．{value} は不正なのでエントリへのパスを書く",
    ),
    "cfg-clone-root-unknown": (
        "`{name}` names root {value}, which is not in `clone.roots`; use a declared root "
        "or declare it",
        "`{name}` の root {value} は `clone.roots` にない．宣言済みの root を使うか宣言する",
    ),
    "cfg-clone-root-table": (
        "`{name}` as a table (a root chosen by a field) is not supported by this release "
        "(mgtk-repo-utils {version}); give one root name, or use a newer release",
        "`{name}` をテーブル（フィールドによる root の振り分け）にする形はこのリリース"
        "（mgtk-repo-utils {version}）では扱えない．root の名前を 1 つ書くか，新しいリリースを使う",
    ),
    "cfg-clone-template": (
        "`{name}` is not a valid template: {value}; write placeholders as `{{key}}` with "
        "a key matching [A-Za-z0-9_-]+, and no other braces",
        "`{name}` はテンプレートとして不正: {value}．差し込みは [A-Za-z0-9_-]+ のキーで "
        "`{{key}}` と書き，それ以外の波括弧は使わない",
    ),
    "cfg-clone-key": (
        "`{name}` must name a key matching [A-Za-z0-9_-]+, or be empty, got {value}; "
        "write the key's name",
        "`{name}` は [A-Za-z0-9_-]+ に一致するキーの名前か空でなければならない．{value} は不正なので"
        "キーの名前を書く",
    ),
}
