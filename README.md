# dev-environment

This repository provides shared top-level files for module repositories via
[Copier](https://copier.readthedocs.io/).

## Initialize in a module repository

```bash
copier copy --vcs-ref main gh:OpenAutomatedDriving/dev-environment .
```

## Update in a module repository

```bash
copier update
```

## Local template development

```bash
copier copy --defaults /path/to/dev-environment /path/to/module-repo
```
