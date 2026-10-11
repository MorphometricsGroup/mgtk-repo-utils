# SPDX-License-Identifier: Apache-2.0
"""Messages of the freeze tool(s): message id -> (English, Japanese)."""

MESSAGES: dict[str, tuple[str, str]] = {
    "summary-freeze": (
        "{files} tracked file(s) under {paths} path(s), mode {mode}",
        "{paths} 件のパスの下に追跡ファイル {files} 件，モード {mode}",
    ),
    "freeze-extra": (
        "tracked under the frozen path `{frozen}` but not in `allow`; remove it from the "
        "index (`git rm --cached`) or add it to `allow`.{reason}",
        "凍結パス `{frozen}` の下で追跡されているが `allow` にない．"
        "インデックスから外す（`git rm --cached`）か `allow` に加える．{reason}",
    ),
    "freeze-missing": (
        "listed in `allow` but not tracked under any frozen path; track the file or "
        "remove the entry from `allow`.{reason}",
        "`allow` にあるがどの凍結パスの下でも追跡されていない．"
        "ファイルを追跡するか `allow` から項目を除く．{reason}",
    ),
}
