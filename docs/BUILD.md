# Maintaining the manuscript

The repository home page is the paper's abstract page. The complete manuscript
is in `source/A_Restriction_Theorem_for_Springer_Fibers.tex`; its compiled PDF is also committed at the
repository root so GitHub can display it directly. Formal versions are archived
as Releases, each containing the PDF and the corresponding source.

## Compile locally

With pdfLaTeX and latexmk installed, run from the repository root:

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error -file-line-error -outdir=build source/A_Restriction_Theorem_for_Springer_Fibers.tex
```

The output is `build/A_Restriction_Theorem_for_Springer_Fibers.pdf`. The source contains its bibliography
and needs no external figures or PDF files.

## Prepare a new version

```bash
python3 scripts/bump_version.py --dry-run
python3 scripts/bump_version.py
```

The default increments the patch version (for example, `1.0.0` to `1.0.1`).
Use `--part minor` or `--part major` when appropriate. The helper keeps the
version and date in `VERSION`, `CITATION.cff`, `CITATION.bib`, and the abstract
page in sync. Commit these files together with the manuscript changes.
Update the `Comments` page count in `README.md` if pagination changes. Release
descriptions use this field automatically.

## Automatic publication

Every branch push and pull request compiles the manuscript. After a successful
default-branch build, GitHub Actions updates the root PDF if its contents have
changed. It creates a Release when the current version has not been published.
An existing public Release remains unchanged. Its tag points to a commit that
contains both the manuscript source and the matching PDF.

The PDF update uses GitHub's own workflow token and does not trigger another
push workflow. A superseded build cannot overwrite a newer default-branch commit
or create a Release for that outdated build.
PDF time metadata is derived from the last manuscript-source commit to reduce
changes caused only by rebuilding. A workflow rerun can finish a partially
completed publication.

The build artifact is kept for 30 days; committed PDFs and Release attachments
provide the persistent reading and versioned-download links.
