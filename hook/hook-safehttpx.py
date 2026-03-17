from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata

datas, binaries, hiddenimports = collect_all("safehttpx")
datas += collect_data_files("safehttpx", include_py_files=True)
datas += copy_metadata("safehttpx")

module_collection_mode = "pyz+py"