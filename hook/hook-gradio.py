from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata

datas, binaries, hiddenimports = collect_all("gradio")
datas += collect_data_files("gradio", include_py_files=True)
datas += copy_metadata("gradio")

# 让包目录和源码/pyc 也能落在文件系统中，降低运行时按路径找资源时出错的概率
module_collection_mode = "pyz+py"