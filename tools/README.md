# PDF 排版工具

本目录包含把仓库 Markdown 重新排成中文精装 PDF 的脚本。生成物位于仓库根目录：

- `前线部署工程师（FDE）精排版-v1.0.24.pdf` —— 全书 13 章，封面、章节页、带页码目录、PDF 书签、页眉页脚、引用框与表格重排；正文与原著 Markdown 一致。
- `FDE-开源全景综合研读报告-2026-11.pdf` —— 以本书为基线，综合 11 个高星 FDE 开源仓库写成的交叉研读报告；源文件见 `research/FDE-开源生态综合研读.md`。

两份 PDF 共用同一套排版引擎 `build_pdfs.py`（ReportLab + Noto Serif SC / Noto Sans SC / JetBrains Mono）。

## 依赖

```bash
python3 -m venv .venv-pdf
.venv-pdf/bin/pip install reportlab fonttools markdown beautifulsoup4 pymupdf
```

- 字体与封面素材**不纳入 Git**，放在 `$FDE_ASSETS`（默认 `/home/user/assets`）：
  - `fonts/NotoSansSC-Regular.ttf`、`NotoSansSC-Bold.ttf`
  - `fonts/NotoSerifSC-Regular.ttf`、`NotoSerifSC-Bold.ttf`
  - `fonts/JetBrainsMono-Regular.ttf`
  - `cover_book.png`、`cover_synthesis.png`（抽象封面插画）
- `prepare_fonts.py` 通过 `gh api` 从 `google/fonts` 取得 OFL 变量字体并实例化静态字重；封面图为生成式插画，需要单独放置。

## 重新生成

```bash
FDE_ASSETS=/home/user/assets .venv-pdf/bin/python tools/prepare_fonts.py
FDE_ASSETS=/home/user/assets .venv-pdf/bin/python tools/build_pdfs.py
```

`build_pdfs.py` 用 `TableOfContents` + `multiBuild` 做三遍排版以解析目录页码，并写入 PDF 大纲书签。目录、章节页、页眉页脚均由脚本自动生成；新增章节只需修改根目录的 Markdown 或 `research/` 下的报告源文件。

## 版权

- 全书正文著作权归范冰所有，沿用仓库 README 的免费阅读与非商业性分享声明。
- 综合研读报告为原创综合叙述，逐项标注来源仓库；二次分发前请核对第 13 章的许可速查表。
- 字体采用 SIL Open Font License；封面插画为本会话生成。
