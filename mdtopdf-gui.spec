# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('C:\\Users\\Lenovo\\PycharmProjects\\MdToPdf\\mdtopdf\\assets', 'mdtopdf/assets'), ('C:\\Users\\Lenovo\\PycharmProjects\\MdToPdf\\mdtopdf\\config\\default_config.yaml', 'mdtopdf/config')]
binaries = [('C:\\Program Files\\GTK3-Runtime Win64\\bin\\libgobject-2.0-0.dll', '.'), ('C:\\Program Files\\GTK3-Runtime Win64\\bin\\libglib-2.0-0.dll', '.'), ('C:\\Program Files\\GTK3-Runtime Win64\\bin\\libgio-2.0-0.dll', '.'), ('C:\\Program Files\\GTK3-Runtime Win64\\bin\\libgmodule-2.0-0.dll', '.'), ('C:\\Program Files\\GTK3-Runtime Win64\\bin\\libpango-1.0-0.dll', '.'), ('C:\\Program Files\\GTK3-Runtime Win64\\bin\\libpangocairo-1.0-0.dll', '.'), ('C:\\Program Files\\GTK3-Runtime Win64\\bin\\libpangoft2-1.0-0.dll', '.'), ('C:\\Program Files\\GTK3-Runtime Win64\\bin\\libpangowin32-1.0-0.dll', '.'), ('C:\\Program Files\\GTK3-Runtime Win64\\bin\\libcairo-2.dll', '.'), ('C:\\Program Files\\GTK3-Runtime Win64\\bin\\libcairo-gobject-2.dll', '.'), ('C:\\Program Files\\GTK3-Runtime Win64\\bin\\libharfbuzz-0.dll', '.'), ('C:\\Program Files\\GTK3-Runtime Win64\\bin\\libfreetype-6.dll', '.'), ('C:\\Program Files\\GTK3-Runtime Win64\\bin\\libfontconfig-1.dll', '.'), ('C:\\Program Files\\GTK3-Runtime Win64\\bin\\libpixman-1-0.dll', '.'), ('C:\\Program Files\\GTK3-Runtime Win64\\bin\\libpng16-16.dll', '.'), ('C:\\Program Files\\GTK3-Runtime Win64\\bin\\zlib1.dll', '.'), ('C:\\Program Files\\GTK3-Runtime Win64\\bin\\libintl-8.dll', '.'), ('C:\\Program Files\\GTK3-Runtime Win64\\bin\\libwinpthread-1.dll', '.'), ('C:\\Program Files\\GTK3-Runtime Win64\\bin\\libgcc_s_seh-1.dll', '.'), ('C:\\Program Files\\GTK3-Runtime Win64\\bin\\libstdc++-6.dll', '.')]
hiddenimports = ['mdtopdf', 'mdtopdf.gui', 'mdtopdf.gui.app', 'mdtopdf.gui.preview', 'mdtopdf.core', 'mdtopdf.core.parser', 'mdtopdf.core.assembler', 'mdtopdf.core.pdf_generator', 'mdtopdf.core.previewer', 'mdtopdf.core.renderer', 'mdtopdf.core.renderer.base', 'mdtopdf.core.renderer.plantuml_renderer', 'mdtopdf.core.renderer.mermaid_renderer', 'mdtopdf.config', 'mdtopdf.config.config_loader', 'mdtopdf.config.models', 'mdtopdf.utils', 'mdtopdf.utils.logger', 'mdtopdf.utils.temp_manager', 'mdtopdf.utils.file_utils', 'weasyprint', 'weasyprint.css', 'weasyprint.document', 'weasyprint.drawing', 'weasyprint.fonts', 'weasyprint.html', 'weasyprint.images', 'weasyprint.layout', 'weasyprint.stacking', 'weasyprint.text', 'weasyprint.text.ffi', 'weasyprint.text.fonts', 'weasyprint.text.line_break', 'fitz', 'PIL', 'PIL.Image', 'PIL.ImageTk', 'PIL._imaging', 'pygments', 'pygments.formatters', 'pygments.formatters.html', 'pygments.lexers', 'pygments.lexers._mapping', 'pygments.styles', 'jinja2', 'jinja2.ext', 'yaml', 'frontmatter', 'cffi', 'pydyf', 'tinycss2', 'tinyhtml5', 'cssselect2', 'pyphen', 'fonttools', 'zopfli', 'brotli']
tmp_ret = collect_all('weasyprint')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pygments')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('fitz')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['C:\\Users\\Lenovo\\PycharmProjects\\MdToPdf\\gui_entry.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='mdtopdf-gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='mdtopdf-gui',
)
