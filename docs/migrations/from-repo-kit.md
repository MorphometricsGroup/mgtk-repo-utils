# Moving from a repo-kit copy to mgtk-repo-utils

For a repository that holds a copy of repo-kit 0.3.x (`vendor/repo-kit/` or
`tools/repo-kit/`). One commit; views are unchanged.

1. Delete the copy and its exclusions from formatters and content lints.
2. Rename `repo-kit.toml` to `mgtk-repo-utils.toml`; set `requires = "0.1"`.
   The tables and keys are the same.
3. Replace the `repo: local` hooks by this hook repository, pinned by commit:

   ```yaml
   repos:
     - repo: https://github.com/MorphometricsGroup/mgtk-repo-utils
       rev: <full commit>  # frozen: v0.1.1
       hooks:
         - id: mgtk-repo-utils-issues-view
           args: [--write]
         - id: mgtk-repo-utils-check
   ```

   `repo-kit-issues-view` becomes `mgtk-repo-utils-issues-view`; `repo-kit-verify`
   has no successor (`mgtk-repo-utils-check` covers every configured tool and the
   pin). `prek update --freeze` writes the commit and the comment.
4. Recipes that ran `python3 -B vendor/repo-kit <tool>` run `mgtk-repo-utils
   <tool>` from the machine's installation
   (`uv tool install "git+https://github.com/MorphometricsGroup/mgtk-repo-utils@<tag>"`),
   or `prek run <hook id> --all-files` for the pinned release.
