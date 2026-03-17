from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata

datas, binaries, hiddenimports = collect_all("gradio_client")
datas += collect_data_files("gradio_client", include_py_files=True)
datas += copy_metadata("gradio_client")

module_collection_mode = "pyz+py"